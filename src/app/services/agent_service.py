from collections.abc import Mapping, Sequence
from typing import Any

from langchain.messages import HumanMessage

from src.app.agent.agent import criarAgente
from src.app.agent.memory import delete_thread

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
    }


# TODO
def transformarDadosProcessoIn(dadosProcesso: dict[str, Any] | None) -> dict[str, Any] | None:
    if dadosProcesso is None:
        return None

    return dadosProcesso


# TODO
def transformarDadosProcessoOut(message: Any):
    if message is None:
        return None

    return message


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
