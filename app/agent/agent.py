from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver  


from app.agent.prompts import SYSTEM_PROMPT
from app.config.settings import settings
from app.agent.tools import teste_tool


def criar_agente():

    model = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key
    )

    agent = create_agent(
        model=model,
        tools=[teste_tool],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver()
        )

    return agent