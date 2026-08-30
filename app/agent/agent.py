from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import testeTool
from app.config.settings import settings


memory_store = InMemorySaver()


def criarAgente():
    model = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key,
    )

    agent = create_agent(
        model=model,
        tools=[testeTool],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=memory_store,
    )

    return agent


agent = criarAgente()