from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver

from app.src.agent.graph import criarGrafoAgente
from app.src.agent.graph_state import AgentState, MessagesState
from app.src.agent.tools import testeTool
from app.src.config.settings import settings

memory_store = InMemorySaver()


def criarAgente():
    """
    Instancia o modelo LLM do Google Gemini, define as ferramentas disponíveis
    e constrói o grafo de estado com memória (checkpointer).
    """
    model = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key,
    )

    ferramentas = [testeTool]

    return criarGrafoAgente(    
        model=model,
        tools=ferramentas,
        checkpointer=memory_store,
    )


agent = criarAgente()

__all__ = ["agent", "criarAgente", "memory_store", "AgentState", "MessagesState"]