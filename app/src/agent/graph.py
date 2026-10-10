import json
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.src.agent.graph_state import AgentState
from app.src.agent.prompts import SYSTEM_PROMPT


def build_mesage(state: AgentState) -> list[BaseMessage]:
    """
    Prepara a lista de mensagens a ser enviada ao modelo,
    injetando o SYSTEM_PROMPT e as informações contextuais de 'dados_processo', se existirem.
    """
    mensagens = list(state.get("messages", []))
    dados_processo = state.get("dados_processo")

    instrucoes = SYSTEM_PROMPT
    if dados_processo:
        try:
            dados_formatados = json.dumps(dados_processo, ensure_ascii=False, indent=2)
        except Exception:
            dados_formatados = str(dados_processo)
        instrucoes += (
            f"\n\n--- DADOS DO PROCESSO ATUAL ---\n"
            f"{dados_formatados}\n"
            f"Utilize esses dados quando o usuário solicitar informações do processo."
        )

    # Se a primeira mensagem já for um SystemMessage, atualiza; senão, insere no início
    if mensagens and isinstance(mensagens[0], SystemMessage):
        return [SystemMessage(content=instrucoes)] + mensagens[1:]
    return [SystemMessage(content=instrucoes)] + mensagens


# Aliases para compatibilidade
build_message = build_mesage
montar_mensagens_modelo = build_mesage



def create_agent_node(model_with_tools: Any) -> RunnableLambda:
    """
    Cria o nó 'agent' responsável por invocar o LLM com suporte tanto síncrono quanto assíncrono.
    """
    def _agent_sync(state: AgentState) -> dict[str, Any]:
        mensagens_para_modelo = build_mesage(state)
        resposta = model_with_tools.invoke(mensagens_para_modelo)
        chamadas = state.get("llm_calls", 0) + 1
        return {
            "messages": [resposta],
            "llm_calls": chamadas,
        }

    async def _agent_async(state: AgentState) -> dict[str, Any]:
        mensagens_para_modelo = build_mesage(state)
        resposta = await model_with_tools.ainvoke(mensagens_para_modelo)
        chamadas = state.get("llm_calls", 0) + 1
        return {
            "messages": [resposta],
            "llm_calls": chamadas,
        }

    return RunnableLambda(_agent_sync, afunc=_agent_async)



def should_continue(state: AgentState) -> str:
    """
    Determina a próxima transição após o nó do agente.
    Se o modelo gerou chamadas de ferramentas (tool_calls), redireciona para o nó 'tools'.
    Caso contrário, finaliza o fluxo (END).
    """
    mensagens = state.get("messages", [])
    if not mensagens:
        return END

    ultima_mensagem = mensagens[-1]
    tool_calls = getattr(ultima_mensagem, "tool_calls", None)
    if tool_calls and len(tool_calls) > 0:
        return "tools"

    return END


def criarGrafoAgente(model: Any, tools: list[Any], checkpointer: Any = None):
    """
    Cria, conecta os nós e compila o grafo do agente LangGraph.

    Nós:
        - 'agent': processa as mensagens, injeta o prompt do sistema/dados de processo e chama o LLM.
        - 'tools': executa as ferramentas solicitadas pelo modelo via ToolNode.

    Arestas (Edges):
        - START -> 'agent'
        - 'agent' -> conditional_edges (should_continue):
            - Se há tool_calls -> 'tools'
            - Caso contrário -> END
        - 'tools' -> 'agent' (retorna o resultado da ferramenta para o LLM gerar a resposta final)
    """
    model_with_tools = model.bind_tools(tools) if tools else model

    workflow = StateGraph(AgentState)

    # 1. Adiciona os nós
    workflow.add_node("agent", create_agent_node(model_with_tools))
    workflow.add_node("tools", ToolNode(tools))

    # 2. Configura as ligações dos nós (arestas)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END,
        },
    )
    workflow.add_edge("tools", "agent")

    # 3. Compilação do grafo com checkpointer opcional
    return workflow.compile(checkpointer=checkpointer)
