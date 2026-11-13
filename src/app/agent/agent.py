from langchain_google_genai import ChatGoogleGenerativeAI

from src.app.agent.graph import criarGrafoAgente
from src.app.agent.graph_state import AgentState, MessagesState
from src.app.agent.memory import memory_store
from src.app.agent.tools import gerarEventoIcs, testeTool
from src.app.config.settings import settings


def criarAgente():
    """
    Instancia o modelo LLM do Google Gemini, define as ferramentas disponíveis
    e constrói o grafo de estado com memória (checkpointer).
    """
    model = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key,
    )

    ferramentas = [testeTool, gerarEventoIcs]

    return criarGrafoAgente(    
        model=model,
        tools=ferramentas,
        checkpointer=memory_store,
    )


agent = criarAgente()

__all__ = ["agent", "criarAgente", "memory_store", "AgentState", "MessagesState"]