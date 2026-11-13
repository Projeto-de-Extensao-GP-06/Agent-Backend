from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage

from src.app.agent.agent import criarAgente
from src.app.agent.memory import delete_thread
from src.app.agent.tools import compilar_anexo_ics
from src.app.services.anonymizer import (
    anonimizar_dados_processo,
    anonimizar_texto,
    desanonimizar_texto,
    extrair_termos_sensiveis_processo,
    limpar_cofre_sessao,
    obter_cofre_sessao,
)

from src.app.services.guardrails import (
    GuardrailViolation,
    aviso_bloqueio_entrada,
    aviso_bloqueio_saida,
    validar_entrada,
    validar_saida,
    validar_saida_segura,
)

agent = criarAgente()

# Cache em memória por sessão para reaproveitar termos sensíveis e tokens do processo entre turnos
_sessao_termos_conhecidos: dict[str, list[str]] = {}
_sessao_mapa_tokens: dict[str, dict[str, str]] = {}


def _extrair_anexos_ics_turno(mensagens: Sequence[Any]) -> list[dict[str, str]]:
    """
    Extrai e compila anexos .ics apenas das ToolMessages geradas após a última HumanMessage
    (evita reenviar arquivos de turnos anteriores armazenados no checkpointer).
    """
    indice_inicio = 0
    for idx in range(len(mensagens) - 1, -1, -1):
        if isinstance(mensagens[idx], HumanMessage) or getattr(mensagens[idx], "type", None) == "human":
            indice_inicio = idx + 1
            break

    anexos: list[dict[str, str]] = []
    for msg in mensagens[indice_inicio:]:
        eh_tool = isinstance(msg, ToolMessage) or getattr(msg, "type", None) == "tool"
        artifact = getattr(msg, "artifact", None)
        if eh_tool and isinstance(artifact, Mapping) and artifact.get("data_inicio"):
            anexos.append(compilar_anexo_ics(dict(artifact)))

    return anexos


async def executarPipelineAgente(
    mensagem: str,
    idSessao: str,
    dadosProcesso: dict[str, Any] | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    mensagemNormalizada = mensagem.strip()
    if not mensagemNormalizada:
        raise ValueError("A mensagem nao pode estar vazia")

    mapa_tokens = _sessao_mapa_tokens.setdefault(idSessao, {})

    if dadosProcesso is not None:
        termos_atuais = extrair_termos_sensiveis_processo(dadosProcesso)
        termos_sessao = _sessao_termos_conhecidos.setdefault(idSessao, [])
        for termo in termos_atuais:
            if termo not in termos_sessao:
                termos_sessao.append(termo)
        processo = transformarDadosProcessoIn(
            dadosProcesso,
            mapaTokens=mapa_tokens,
            idSessao=idSessao,
        )
    else:
        processo = None
        termos_sessao = _sessao_termos_conhecidos.get(idSessao, [])

    mensagemAnonimizada = transformarMensagemIn(
        mensagemNormalizada,
        dadosProcesso=dadosProcesso,
        termosConhecidos=termos_sessao,
        mapaTokens=mapa_tokens,
        idSessao=idSessao,
    )

    async def _invocar(conteudo: str) -> tuple[dict[str, Any], list[Any], str]:
        estado_inicial: dict[str, Any] = {
            "messages": [HumanMessage(content=conteudo)],
            "dados_processo": processo,
        }
        if timezone:
            estado_inicial["timezone"] = timezone

        resp = await agent.ainvoke(
            estado_inicial,
            {"configurable": {"thread_id": idSessao}, "recursion_limit": 10},
        )
        msgs = resp.get("messages", [])
        if not msgs:
            raise RuntimeError("O assistente nao retornou uma resposta")
        return resp, msgs, conteudoParaTexto(msgs[-1].content)

    guardrail_acionado: dict[str, str] | None = None

    # Guardrail de entrada: após a anonimização (Presidio), antes do LLM.
    # Em caso de violação, o modelo é avisado e responde ao usuário.
    try:
        mensagemAnonimizada = validar_entrada(mensagemAnonimizada)
        conteudo_para_modelo = mensagemAnonimizada
    except GuardrailViolation as violacao:
        guardrail_acionado = {"etapa": "entrada", "motivo": str(violacao)}
        conteudo_para_modelo = aviso_bloqueio_entrada(str(violacao))

    agent_response, mensagens, message = await _invocar(conteudo_para_modelo)

    # Guardrail de saída: sobre a resposta ainda anonimizada, antes da desanonimização
    if guardrail_acionado is None:
        try:
            message = validar_saida(message)
        except GuardrailViolation as violacao:
            guardrail_acionado = {"etapa": "saida", "motivo": str(violacao)}
            agent_response, mensagens, message = await _invocar(
                aviso_bloqueio_saida(str(violacao))
            )
            message = validar_saida_segura(message)

    resposta = transformarDadosProcessoOut(message, idSessao=idSessao)

    if not resposta:
        raise RuntimeError("O assistente retornou uma resposta sem texto")

    anexos_ics = _extrair_anexos_ics_turno(mensagens)

    return {
        "resposta": resposta,
        "attachments": anexos_ics,
        "raw_response": agent_response,
        "debug_info": {
            "mensagem_original": mensagemNormalizada,
            "mensagem_anonimizada": mensagemAnonimizada,
            "dados_processo_original": dadosProcesso,
            "dados_processo_anonimizado": processo or agent_response.get("dados_processo"),
            "mapa_anonimizacao": obter_cofre_sessao(idSessao).exportar_mapa(),
            "retorno_modelo": message,
            "pos_desanonimizacao": resposta,
            "llm_calls": agent_response.get("llm_calls", 1),
            "mensagens": mensagens,
            "guardrail": guardrail_acionado,
        },
    }


def transformarMensagemIn(
    mensagem: str,
    dadosProcesso: dict[str, Any] | None = None,
    termosConhecidos: Sequence[str] | None = None,
    mapaTokens: dict[str, str] | None = None,
    idSessao: str | None = None,
) -> str:
    """
    Anonimiza os dados sensíveis do texto enviado pelo usuário antes do envio ao agente/LLM.
    Limita-se a padrões determinísticos (CPF, CNPJ, RG, Telefone, E-mail, CNJ, Razão Social)
    e aos nomes/identificadores reais extraídos de `dadosProcesso`.
    """
    if not mensagem or not isinstance(mensagem, str):
        return mensagem

    termos: list[str] = list(termosConhecidos) if termosConhecidos else []
    if dadosProcesso is not None:
        for t in extrair_termos_sensiveis_processo(dadosProcesso):
            if t not in termos:
                termos.append(t)

    texto_anonimizado, _ = anonimizar_texto(
        mensagem,
        termos_conhecidos=termos or None,
        mapa_tokens=mapaTokens,
        session_id=idSessao,
    )
    return texto_anonimizado


def transformarDadosProcessoIn(
    dadosProcesso: dict[str, Any] | None,
    mapaTokens: dict[str, str] | None = None,
    idSessao: str | None = None,
) -> dict[str, Any] | None:
    """Anonimiza os dados sensíveis do processo antes do envio ao agente/LLM."""
    if dadosProcesso is None:
        return None

    return anonimizar_dados_processo(
        dadosProcesso,
        mapa_tokens=mapaTokens,
        session_id=idSessao,
    )


def transformarDadosProcessoOut(message: Any, idSessao: str | None = None) -> Any:
    """Restaura dados sensíveis presentes na resposta do agente/LLM."""
    if not isinstance(message, str):
        return message

    return desanonimizar_texto(message, session_id=idSessao)


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
    _sessao_termos_conhecidos.pop(idSessao, None)
    _sessao_mapa_tokens.pop(idSessao, None)
    limpar_cofre_sessao(idSessao)
    return delete_thread(idSessao)


__all__ = [
    "agent",
    "executarPipelineAgente",
    "transformarMensagemIn",
    "transformarDadosProcessoIn",
    "transformarDadosProcessoOut",
    "conteudoParaTexto",
    "excluirSessao",
]
