import asyncio
import os
import uuid
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv(override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SESSION_ID = str(uuid.uuid4())

async def main():

    client = MultiServerMCPClient({
        "Network Tools": {
            "transport": "sse",
            "url": "http://127.0.0.1:8000/sse"
        }
    })

    tools = await client.get_tools()

    llm = ChatGoogleGenerativeAI(
        model='gemini-2.0-flash',
        google_api_key=GEMINI_API_KEY,
        temperature=0.3
    )

    system_prompt = f""" you are a cybersecurity expert. You have access to the following tools: {tools}."""

    checkpointer = InMemorySaver()

    agent = create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        prompt=system_prompt
    )

    while True:
        raw_input_text = input("Enter your query (or 'exit' to quit): ")
        if raw_input_text.lower() == 'exit':
            break

        response = await agent.ainvoke(
            {"messages": [
                {"role": "user", "content": raw_input_text}
            ]},
            config={"configurable": {"thread_id": SESSION_ID}}
        )

        print("\n\n\nResponse:" + response["messages"][-1].content + "\n\n\n")

if __name__ == "__main__":
    asyncio.run(main())