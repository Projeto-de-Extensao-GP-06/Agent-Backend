from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.settings import settings


def criar_agente():

    model = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key
    )

    agent = create_agent(
        model=model,
        tools=None,
        system_prompt=None
    )

    return agent