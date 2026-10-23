from typing import Annotated, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def _atualizar_dados_processo(
        antigo: dict[str, Any] | None, 
        novo: dict[str, Any] | None 
        ) -> dict[str, Any] | None:
    """
    Função redutora para 'dados_processo'.
    Preserva os dados de processo já carregados na memória da thread caso a mensagem
    atual venha com dados_processo=None. Se um novo dicionário for enviado, atualiza.
    """
    return novo if novo is not None else antigo



class AgentState(TypedDict, total=False):
    """
    Estado compartilhado do grafo do agente (MarIA).

    Atributos:
        messages: Histórico acumulado de mensagens da conversa (HumanMessage, AIMessage, ToolMessage),
                  gerenciado via add_messages do LangGraph.
        dados_processo: Informações contextuais do processo jurídico (partes, números, prioridade, etc.).
        llm_calls: Contador de invocações realizadas ao modelo durante a execução.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    dados_processo: Annotated[dict[str, Any] | None, _atualizar_dados_processo]
    llm_calls: int
    


# Alias para retrocompatibilidade com referências a MessagesState
MessagesState = AgentState

__all__ = ["AgentState", "MessagesState", "_atualizar_dados_processo"]