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


def _extrair_chave_periodo(dados: dict[str, Any]) -> str:
    periodo = dados.get("periodo") if isinstance(dados.get("periodo"), dict) else {}
    date_from = str(periodo.get("dateFrom") or dados.get("dateFrom") or "")
    date_to = str(periodo.get("dateTo") or dados.get("dateTo") or "")
    applied = str(periodo.get("appliedPeriod") or dados.get("appliedPeriod") or "")
    if date_from or date_to:
        return f"{applied} ({date_from} a {date_to})".strip()
    return applied or "periodo_padrao"


def _atualizar_dados_dashboard(
        antigo: dict[str, Any] | None,
        novo: dict[str, Any] | None,
        ) -> dict[str, Any] | None:
    """
    Função redutora para 'dados_dashboard'.
    Preserva os dados da dashboard já carregados na thread caso 'novo' seja None,
    e acumula snapshots de períodos anteriores em 'historico_periodos' quando o
    usuário troca o filtro de período durante a mesma conversa.
    """
    if novo is None:
        return antigo

    if not isinstance(novo, dict):
        return antigo

    historico: dict[str, Any] = {}
    if isinstance(antigo, dict):
        hist_antigo = antigo.get("historico_periodos")
        if isinstance(hist_antigo, dict):
            historico.update(hist_antigo)
        chave_antiga = _extrair_chave_periodo(antigo)
        copia_antiga = {k: v for k, v in antigo.items() if k != "historico_periodos"}
        if copia_antiga:
            historico[chave_antiga] = copia_antiga

    chave_nova = _extrair_chave_periodo(novo)
    copia_nova = {k: v for k, v in novo.items() if k != "historico_periodos"}
    historico[chave_nova] = copia_nova

    resultado = dict(copia_nova)
    resultado["historico_periodos"] = historico
    return resultado


def _atualizar_timezone(
        antigo: str | None,
        novo: str | None,
        ) -> str | None:
    """Preserva o fuso horário da sessão caso não seja reenviado no turno atual."""
    return novo if novo is not None else antigo


class AgentState(TypedDict, total=False):
    """
    Estado compartilhado do grafo do agente (MarIA).

    Atributos:
        messages: Histórico acumulado de mensagens da conversa (HumanMessage, AIMessage, ToolMessage),
                  gerenciado via add_messages do LangGraph.
        dados_processo: Informações contextuais do processo jurídico (partes, números, prioridade, etc.).
        dados_dashboard: Indicadores gerais e filtrados por período da Dashboard do SGPJ.
        timezone: Fuso horário IANA do usuário (ex: America/Sao_Paulo) para referência de data/hora.
        llm_calls: Contador de invocações realizadas ao modelo durante a execução.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    dados_processo: Annotated[dict[str, Any] | None, _atualizar_dados_processo]
    dados_dashboard: Annotated[dict[str, Any] | None, _atualizar_dados_dashboard]
    timezone: Annotated[str | None, _atualizar_timezone]
    llm_calls: int
    


# Alias para retrocompatibilidade com referências a MessagesState
MessagesState = AgentState

__all__ = [
    "AgentState",
    "MessagesState",
    "_atualizar_dados_processo",
    "_atualizar_dados_dashboard",
    "_atualizar_timezone",
]