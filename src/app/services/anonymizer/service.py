import logging
import re
from typing import Any

from presidio_anonymizer.entities import OperatorConfig, OperatorResult
from presidio_anonymizer.operators.aes_cipher import AESCipher

from src.app.config.settings import settings
from src.app.services.anonymizer.engine import (
    get_analyzer_engine,
    get_anonymizer_engine,
    get_deanonymize_engine,
)

logger = logging.getLogger(__name__)

# Padrão de regex para identificar tokens criptografados com AESCipher (Base64 URL-safe >= 43 chars)
ENCRYPTED_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43,}={0,2}")


def anonimizar_texto(texto: str, key: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """
    Analisa e anonimiza o texto utilizando criptografia reversível AES.
    Retorna o texto criptografado e a lista de itens/metadados das entidades criptografadas.
    """
    if not texto or not isinstance(texto, str):
        return texto, []

    encryption_key = key or settings.anonymization_key
    analyzer = get_analyzer_engine()
    anonymizer = get_anonymizer_engine()

    try:
        results = analyzer.analyze(text=texto, language="pt")
    except Exception as e:
        logger.warning("Falha ao analisar texto no idioma 'pt': %s", e)
        results = []

    if not results:
        return texto, []

    operators = {
        "DEFAULT": OperatorConfig("encrypt", {"key": encryption_key})
    }

    anonymized = anonymizer.anonymize(
        text=texto,
        analyzer_results=results,
        operators=operators,
    )

    items = [
        {
            "start": item.start,
            "end": item.end,
            "entity_type": item.entity_type,
            "text": item.text,
            "operator": item.operator,
        }
        for item in anonymized.items
    ]

    return anonymized.text, items


def anonimizar_dados_processo(dados: dict[str, Any] | None, key: str | None = None) -> dict[str, Any] | None:
    """
    Percorre recursivamente a estrutura de dados (dicionário ou lista) e
    anonimiza todos os campos de texto com dados pessoais identificáveis (PII).
    """
    if dados is None:
        return None

    def _anonimizar_recursivo(valor: Any) -> Any:
        if isinstance(valor, dict):
            return {k: _anonimizar_recursivo(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [_anonimizar_recursivo(item) for item in valor]
        if isinstance(valor, str):
            texto_anonimizado, _ = anonimizar_texto(valor, key=key)
            return texto_anonimizado
        return valor

    return _anonimizar_recursivo(dados)


def desanonimizar_texto(texto: str, key: str | None = None) -> str:
    """
    Identifica tokens criptografados presentes no texto (ex: gerados pelo LLM)
    e restaura os dados originais através do DeanonymizeEngine e AESCipher.
    """
    if not texto or not isinstance(texto, str):
        return texto

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")
    matches = list(ENCRYPTED_TOKEN_PATTERN.finditer(texto))

    if not matches:
        return texto

    entities: list[OperatorResult] = []
    for m in matches:
        token = m.group()
        try:
            # Valida se o token é decifrável pela chave AES
            AESCipher.decrypt(key=key_bytes, text=token)
            entities.append(
                OperatorResult(
                    start=m.start(),
                    end=m.end(),
                    entity_type="ENCRYPTED_PII",
                )
            )
        except Exception:
            # Se não decifrar, é apenas uma palavra normal ou token não gerado por esta chave
            continue

    if not entities:
        return texto

    deanonymizer = get_deanonymize_engine()
    operators = {
        "DEFAULT": OperatorConfig("decrypt", {"key": encryption_key})
    }

    try:
        resultado = deanonymizer.deanonymize(
            text=texto,
            entities=entities,
            operators=operators,
        )
        return resultado.text
    except Exception as e:
        logger.error("Erro ao desanonimizar texto com o DeanonymizeEngine: %s", e)
        return texto
