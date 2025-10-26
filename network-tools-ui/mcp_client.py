import os
import asyncio
from dotenv import load_dotenv
from google.cloud import firestore
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph.message import REMOVE_ALL_MESSAGES


load_dotenv(override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
DOCUMENT_NAME = os.getenv("DOCUMENT_NAME")

# --- Firestore Setup ---
db = firestore.Client(project=PROJECT_ID)
doc_ref = db.collection(COLLECTION_NAME).document(DOCUMENT_NAME)


async def main():
    # --- Load existing chat ---
    doc_snapshot = doc_ref.get()
    chat_history = doc_snapshot.to_dict().get("messages", []) if doc_snapshot.exists else []

    # Convert Firestore chat history to langchain message objects
    converted_history = []
    for msg in chat_history:
        if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
            print(f"Skipping malformed message: {msg}")
            continue
        if msg["role"] == "user":
            converted_history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            converted_history.append(AIMessage(content=msg["content"]))

    # --- In-Memory Checkpointer ---
    checkpointer = InMemorySaver()

    # --- MCP client ---
    client = MultiServerMCPClient({
        "Network Tools": {
            "transport": "sse",
            "url": "http://127.0.0.1:8000/sse"
        }
    })
    tools = await client.get_tools()

    # --- LLM ---
    llm = ChatGoogleGenerativeAI(
        model='gemini-2.0-flash',
        google_api_key=GEMINI_API_KEY,
        temperature=0.3
    )

    system_prompt = f""" you are a cybersecurity expert. You have access to the following tools: {tools}."""

    # --- Agent with checkpointer ---
    agent = create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        prompt=system_prompt
    )

    # --- Seed thread state with Firestore history (recommended way) ---
    thread_config = {"configurable": {"thread_id": "main_session"}}
    if converted_history:
        try:
            # Clear any existing messages for this thread, then load Firestore history
            await agent.aupdate_state(
                thread_config,
                {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *converted_history]},
            )
        except Exception as e:
            print(f"Error seeding state: {e}")
            return

    # --- Chat loop ---
    while True:
        user_input = input("Enter your query (or 'exit' to quit): ")
        if user_input.lower() == 'exit':
            break

        # Append to Firestore transcript
        chat_history.append({"role": "user", "content": user_input})

        # Invoke agent on the same thread
        response = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=thread_config
        )
        reply = response["messages"][-1].content

        # Append agent reply to Firestore transcript
        chat_history.append({"role": "assistant", "content": reply})

        print("\n\n\nResponse:" + reply + "\n\n\n")

    # --- Persist updated transcript to Firestore ---
    doc_ref.set({"messages": chat_history}, merge=True)


if __name__ == "__main__":
    asyncio.run(main())