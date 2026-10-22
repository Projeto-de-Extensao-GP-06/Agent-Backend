from collections.abc import Mapping, Sequence
from typing import Any

from langchain.messages import HumanMessage

from src.app.agent.agent import criarAgente
from src.app.agent.memory import delete_thread
from src.app.services.anonymizer import (
    anonimizar_dados_processo,
    desanonimizar_texto,
)

agent = criarAgente()


async def executarPipelineAgente(
    mensagem: str,
    idSessao: str,
    dadosProcesso: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mensagemNormalizada = mensagem.strip()
    if not mensagemNormalizada:
        raise ValueError("A mensagem nao pode estar vazia")

    processo = transformarDadosProcessoIn(dadosProcesso) if dadosProcesso != None else None

    agent_response = await agent.ainvoke(
        {
            "messages": [HumanMessage(content=mensagemNormalizada)],
            "dados_processo": processo,
        },
        {"configurable": {"thread_id": idSessao}},
    )

    mensagens = agent_response.get("messages", [])
    if not mensagens:
        raise RuntimeError("O assistente nao retornou uma resposta")

    message = conteudoParaTexto(mensagens[-1].content)

    resposta = transformarDadosProcessoOut(message)

    if not resposta:
        raise RuntimeError("O assistente retornou uma resposta sem texto")

    return {
        "resposta": resposta,
        "raw_response": agent_response,
        "debug_info": {
            "dados_processo_original": dadosProcesso,
            "dados_processo_anonimizado": processo or agent_response.get("dados_processo"),
            "retorno_modelo": message,
            "pos_desanonimizacao": resposta,
            "llm_calls": agent_response.get("llm_calls", 1),
            "mensagens": mensagens,
        },
    }

def transformarDadosProcessoIn(dadosProcesso: dict[str, Any] | None) -> dict[str, Any] | None:
    """Anonimiza os dados sensíveis do processo antes do envio ao agente/LLM."""
    if dadosProcesso is None:
        return None

    return anonimizar_dados_processo(dadosProcesso)


def transformarDadosProcessoOut(message: Any) -> Any:
    """Restaura dados sensíveis criptografados presentes na resposta do agente/LLM."""
    if not isinstance(message, str):
        return message

    return desanonimizar_texto(message)


def conteudoParaTexto(conteudo: Any) -> str:
    if isinstance(conteudo, str):
        return conteudo.strip()

    if isinstance(conteudo, Sequence) and not isinstance(conteudo, (str, bytes)):
        partes: list[str] = []
        for item in conteudo:
            if isinstance(item, Mapping):
                texto = item.get("text")
                if isinstance(texto, str):
                    partes.append(texto)
            elif isinstance(item, str):
                partes.append(item)
        return "".join(partes).strip()

    return ""


def excluirSessao(idSessao: str) -> bool:
    return delete_thread(idSessao)


__all__ = [
    "agent",
    "executarPipelineAgente",
    "transformarDadosProcessoIn",
    "transformarDadosProcessoOut",
    "conteudoParaTexto",
    "excluirSessao",
]
