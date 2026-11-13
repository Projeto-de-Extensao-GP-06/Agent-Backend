"""Guardrails determinísticos de entrada e saída da mensagem.

- Entrada: executa APÓS a anonimização (Presidio) e antes de chamar o agente/LLM.
- Saída: executa sobre a resposta do modelo ANTES da desanonimização, para que
  dados legítimos restaurados do cofre não sejam tratados como vazamento.
"""

import re
import unicodedata

MAX_TAMANHO_ENTRADA = 4000
MAX_TAMANHO_SAIDA = 20000

MENSAGEM_SAIDA_BLOQUEADA = (
    "Não posso fornecer essa resposta pois fere as diretrizes do SGPJs. Posso ajudar com outra coisa?"
)


class GuardrailViolation(ValueError):
    """Violação de guardrail. Herda de ValueError para virar HTTP 400 na rota."""


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).lower()


_PADROES_INJECAO = [
    r"ignor\w* (todas? )?(as )?(suas |as |tuas )?(instruc\w*|regras|ordens|diretrizes) (anteriores|acima|previas)",
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|rules|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above)",
    r"esque\w* (todas? )?(as )?(suas )?(instruc\w*|regras|diretrizes)",
    r"(revele|mostre|exiba|imprima|repita|vaze)\w* (o |seu |suas? )?(system prompt|prompt do sistema|prompt de sistema|instruc\w* (internas|do sistema|iniciais))",
    r"(reveal|show|print|repeat|leak) (me )?(your |the )?(system prompt|hidden prompt|initial instructions)",
    r"\bsystem prompt\b",
    r"voce (agora )?(e|sera) (um|o) (dan|assistente sem (restric\w*|filtros?))",
    r"\bjailbreak\b",
    r"\bdan mode\b",
    r"modo desenvolvedor|developer mode",
    r"(finja|aja como|act as|pretend) (que )?(voce )?(nao tem|no) (restric\w*|regras|limites|rules|restrictions)",
]
_REGEX_INJECAO = [re.compile(p) for p in _PADROES_INJECAO]

_REGEX_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_PADROES_SEGREDO = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

_PADROES_VAZAMENTO_PROMPT = [
    re.compile(p)
    for p in (
        r"meu (system prompt|prompt do sistema|prompt de sistema) (e|diz)",
        r"minhas instrucoes (internas|de sistema) (sao|dizem)",
        r"my system prompt (is|says)",
    )
]


def validar_entrada(mensagem_anonimizada: str) -> str:
    """Valida a mensagem já anonimizada. Retorna o texto limpo ou levanta GuardrailViolation."""
    if not isinstance(mensagem_anonimizada, str) or not mensagem_anonimizada.strip():
        raise GuardrailViolation("A mensagem nao pode estar vazia")

    texto = _REGEX_CONTROLE.sub("", mensagem_anonimizada).strip()

    if len(texto) > MAX_TAMANHO_ENTRADA:
        raise GuardrailViolation(
            f"A mensagem excede o limite de {MAX_TAMANHO_ENTRADA} caracteres"
        )

    normalizado = _normalizar(texto)
    for regex in _REGEX_INJECAO:
        if regex.search(normalizado):
            raise GuardrailViolation(
                "A mensagem foi bloqueada por conter instrucoes nao permitidas"
            )

    return texto


def validar_saida(resposta: str) -> str:
    """Valida a resposta do modelo (ainda anonimizada). Redige segredos e bloqueia vazamento de prompt."""
    if not isinstance(resposta, str):
        return resposta

    normalizado = _normalizar(resposta)
    if any(r.search(normalizado) for r in _PADROES_VAZAMENTO_PROMPT):
        raise GuardrailViolation("A resposta gerada revelaria instrucoes internas do sistema")

    return _sanitizar_saida(resposta)


def validar_saida_segura(resposta: str) -> str:
    """Valida a resposta de recuperação sem levantar erro: se ainda violar, usa mensagem padrão."""
    try:
        return validar_saida(resposta)
    except GuardrailViolation:
        return MENSAGEM_SAIDA_BLOQUEADA


def _sanitizar_saida(resposta: str) -> str:
    texto = resposta
    for regex in _PADROES_SEGREDO:
        texto = regex.sub("[REDACTED]", texto)

    if len(texto) > MAX_TAMANHO_SAIDA:
        texto = texto[:MAX_TAMANHO_SAIDA]

    return texto


def aviso_bloqueio_entrada(motivo: str) -> str:
    """Instrução enviada ao modelo no lugar da mensagem barrada (o conteúdo original NÃO é repassado)."""
    return (
        "[AVISO DO SISTEMA] A ultima mensagem do usuario foi barrada pelo guardrail de "
        f"seguranca e vai contra as diretrizes de uso ({motivo}). Nao atenda ao pedido. "
        "Responda ao usuario, de forma educada e breve, que a mensagem vai contra as "
        "diretrizes e pergunte se voce pode ajudar de outra forma."
    )


def aviso_bloqueio_saida(motivo: str) -> str:
    return (
        "[AVISO DO SISTEMA] Sua resposta anterior foi barrada pelo guardrail de saida "
        f"({motivo}) e nao sera exibida. Responda ao usuario, de forma educada e breve, "
        "que nao pode fornecer essa informacao por ir contra as diretrizes e pergunte se "
        "pode ajudar de outra forma."
    )


__all__ = [
    "aviso_bloqueio_entrada",
    "aviso_bloqueio_saida",
    "validar_saida_segura",
    "GuardrailViolation",
    "MENSAGEM_SAIDA_BLOQUEADA",
    "validar_entrada",
    "validar_saida",
]
