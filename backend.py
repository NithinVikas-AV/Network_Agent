# api_server.py
import os
from contextlib import asynccontextmanager
from typing import List, Dict, Any
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from google.cloud import firestore
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from report_generate import generate_report_for_session

load_dotenv(override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
DOCUMENT_NAME = os.getenv("DOCUMENT_NAME")

db = firestore.Client(project=PROJECT_ID)
doc_ref = db.collection(COLLECTION_NAME).document(DOCUMENT_NAME)

agent = None
thread_config = {"configurable": {"thread_id": "main_session"}}
chat_history_cache: List[Dict[str, Any]] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, chat_history_cache

    # Load chat history from Firestore
    snapshot = doc_ref.get()
    chat_history_cache = snapshot.to_dict().get("messages", []) if snapshot.exists else []

    # Convert to LangChain messages
    converted = []
    for msg in chat_history_cache:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            if msg["role"] == "user":
                converted.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                converted.append(AIMessage(content=msg["content"]))

    # Initialize MCP tools
    client = MultiServerMCPClient({
        "Network Tools": {
            "transport": "sse",
            "url": "http://127.0.0.1:8000/sse"
        }
    })
    tools = await client.get_tools()

    # Initialize Gemini model
    llm = ChatGoogleGenerativeAI(
        model='gemini-2.0-flash',
        google_api_key=GEMINI_API_KEY,
        temperature=0.3
    )

    # System prompt and memory
    system_prompt = f"""  
    You are an autonomous senior cybersecurity analyst agent. You have programmatic access to these tools: subdomain enumeration (sublist3r), nmap port scanning, service fingerprinting (whatweb), OSINT harvesting (theharvester), and directory enumeration (gobuster)
    """
    checkpointer = InMemorySaver()

    agent_local = create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        prompt=system_prompt
    )

    # Restore message history
    if converted:
        try:
            await agent_local.aupdate_state(
                thread_config,
                {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *converted]},
            )
        except Exception as e:
            print("Startup seed failed:", e)

    globals()["agent"] = agent_local

    try:
        yield
    finally:
        pass


app = FastAPI(title="Network Tools API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/history")
async def get_history():
    snapshot = doc_ref.get()
    messages = snapshot.to_dict().get("messages", []) if snapshot.exists else []
    return {"messages": messages}


@app.post("/api/chat")
async def chat(payload: Dict[str, str] = Body(...)):
    global chat_history_cache, agent
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not ready")

    user_text = (payload.get("message") or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Empty message")

    chat_history_cache.append({"role": "user", "content": user_text})
    resp = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_text}]},
        config=thread_config
    )
    reply = resp["messages"][-1].content
    chat_history_cache.append({"role": "assistant", "content": reply})
    doc_ref.set({"messages": chat_history_cache}, merge=True)
    return {"reply": reply}


@app.post("/api/report")
async def generate_report():
    pdf_path = generate_report_for_session(DOCUMENT_NAME, output_dir=".")
    filename = os.path.basename(pdf_path)
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@app.delete("/api/history/clear")
async def clear_history():
    """Clear chat history in Firestore and memory."""
    global chat_history_cache
    chat_history_cache = []
    doc_ref.set({"messages": []}, merge=True)
    return JSONResponse(content={"message": "Chat history cleared successfully."})