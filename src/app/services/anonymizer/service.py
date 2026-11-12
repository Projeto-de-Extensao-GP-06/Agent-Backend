import hashlib
import hmac
import logging
import re
from threading import Lock
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

# Padrão de regex para identificar placeholders curtos gerados pelo cofre de anonimização (ex: [PESSOA_1], [CPF_1])
PLACEHOLDER_PATTERN = re.compile(r"\[[A-Z][A-Z0-9_]*_\d+\]")

# Padrão de regex legado/fallback para identificar tokens criptografados diretamente com AESCipher (Base64 URL-safe >= 43 chars)
ENCRYPTED_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43,}={0,2}")

# Mapeamento de entidades do Presidio para prefixos curtos e legíveis para o LLM
ENTITY_PREFIX_MAP: dict[str, str] = {
    "PERSON": "PESSOA",
    "PER": "PESSOA",
    "BR_CPF": "CPF",
    "BR_CNPJ": "CNPJ",
    "BR_RG": "RG",
    "PHONE_NUMBER": "TELEFONE",
    "BR_RAZAO_SOCIAL": "EMPRESA",
    "BR_CNJ": "PROCESSO_CNJ",
    "EMAIL_ADDRESS": "EMAIL",
    "LOCATION": "LOCAL",
    "LOC": "LOCAL",
    "ORGANIZATION": "ORGANIZACAO",
    "ORG": "ORGANIZACAO",
    "DATE_TIME": "DATA",
    "CREDIT_CARD": "CARTAO",
    "IP_ADDRESS": "IP",
    "IBAN_CODE": "IBAN",
    "NRP": "ENTIDADE",
    "URL": "URL",
}


def _obter_prefixo_entidade(entity_type: str) -> str:
    """Converte o tipo de entidade do Presidio em um prefixo curto para placeholder."""
    prefixo = ENTITY_PREFIX_MAP.get(entity_type)
    if prefixo:
        return prefixo
    normalizado = re.sub(r"[^A-Z0-9_]", "_", entity_type.upper()).strip("_")
    return normalizado or "DADO"


class CofreAnonimizacao:
    """
    Cofre por sessão/contexto que associa placeholders curtos e determinísticos
    (ex: [PESSOA_1], [CPF_1]) aos respectivos valores cifrados em AES-CBC.

    Nenhum dado sensível em texto claro é armazenado neste cofre: o mapeamento
    guarda apenas `placeholder -> token_aes_cifrado` e um resumo HMAC-SHA256
    para garantir que valores idênticos recebam o mesmo placeholder na sessão.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._placeholders: dict[str, str] = {}
        self._hash_to_placeholder: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def registrar(
        self,
        entity_type: str,
        plain_text: str,
        aes_token: str,
        key_bytes: bytes,
    ) -> str:
        """Registra (ou reutiliza) um placeholder curto para uma entidade cifrada."""
        prefixo = _obter_prefixo_entidade(entity_type)
        dedup_key = hmac.new(
            key_bytes,
            f"{prefixo}:{plain_text}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        with self._lock:
            existente = self._hash_to_placeholder.get(dedup_key)
            if existente is not None:
                return existente

            proximo_indice = self._counters.get(prefixo, 0) + 1
            self._counters[prefixo] = proximo_indice
            placeholder = f"[{prefixo}_{proximo_indice}]"

            self._hash_to_placeholder[dedup_key] = placeholder
            self._placeholders[placeholder] = aes_token
            return placeholder

    def obter_token_cifrado(self, placeholder: str) -> str | None:
        """Retorna o token AES criptografado associado a um placeholder, se existir."""
        with self._lock:
            return self._placeholders.get(placeholder)

    def exportar_mapa(self) -> dict[str, str]:
        """Retorna cópia do mapa `placeholder -> token_aes_cifrado` (sem texto claro)."""
        with self._lock:
            return dict(self._placeholders)


_session_vaults_lock = Lock()
_session_vaults: dict[str, CofreAnonimizacao] = {}
_default_vault = CofreAnonimizacao()


def obter_cofre_sessao(session_id: str) -> CofreAnonimizacao:
    """Obtém ou cria o cofre de anonimização isolado para uma sessão."""
    with _session_vaults_lock:
        cofre = _session_vaults.get(session_id)
        if cofre is None:
            cofre = CofreAnonimizacao()
            _session_vaults[session_id] = cofre
        return cofre


def limpar_cofre_sessao(session_id: str) -> bool:
    """Remove o cofre de anonimização associado a uma sessão."""
    with _session_vaults_lock:
        return _session_vaults.pop(session_id, None) is not None


def _resolver_cofre(
    session_id: str | None = None,
    cofre: CofreAnonimizacao | None = None,
) -> CofreAnonimizacao:
    if cofre is not None:
        return cofre
    if session_id:
        return obter_cofre_sessao(session_id)
    return _default_vault

# Termos comuns da língua portuguesa que não devem ser classificados como PII (deny-list)
# Inclui saudações, despedidas, termos de cortesia e verbos/comandos frequentes enviados à assistente.
IGNORAR_ENTIDADES = {
    # Saudações e despedidas
    "olá",
    "ola",
    "oi",
    "oie",
    "alô",
    "alo",
    "tchau",
    "adeus",
    "bom dia",
    "boa tarde",
    "boa noite",
    # Cortesia e solicitações comuns
    "por favor",
    "favor",
    "gentileza",
    "obrigado",
    "obrigada",
    "quero",
    "gostaria",
    "preciso",
    "poderia",
    # Verbos e comandos frequentes enviados à assistente
    "retorne",
    "retornar",
    "retorna",
    "busque",
    "buscar",
    "busca",
    "consulte",
    "consultar",
    "consulta",
    "mostre",
    "mostrar",
    "mostra",
    "liste",
    "listar",
    "lista",
    "verifique",
    "verificar",
    "verifica",
    "faça",
    "faca",
    "fazer",
    "envie",
    "enviar",
    "envia",
    "explique",
    "explicar",
    "explica",
    "gere",
    "gerar",
    "gera",
    "crie",
    "criar",
    "cria",
    "informe",
    "informar",
    "informa",
    "atualize",
    "atualizar",
    "atualiza",
    "cancele",
    "cancelar",
    "cancela",
    "adicione",
    "adicionar",
    "adiciona",
    "remova",
    "remover",
    "remove",
    "altere",
    "alterar",
    "altera",
    "exiba",
    "exibir",
    "exibe",
    "obtenha",
    "obter",
    "obtem",
    "procure",
    "procurar",
    "procura",
    "localize",
    "localizar",
    "localiza",
    "detalhe",
    "detalhar",
    "detalha",
    "descreva",
    "descrever",
    "descreve",
    "esclareça",
    "esclareca",
    "esclarecer",
    "resuma",
    "resumir",
    "resume",
    "analise",
    "analisar",
    "veja",
    "ver",
    "diga",
    "dizer",
    "responda",
    "responder",
    "ajude",
    "ajudar",
    "abra",
    "abrir",
    "feche",
    "fechar",
    "salve",
    "salvar",
    "baixe",
    "baixar",
    "imprima",
    "imprimir",
    "confira",
    "conferir",
    "acesse",
    "acessar",
}


def anonimizar_texto(
    texto: str,
    key: str | None = None,
    session_id: str | None = None,
    cofre: CofreAnonimizacao | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Analisa e anonimiza o texto substituindo PII por placeholders curtos (ex: [PESSOA_1])
    e armazenando o respectivo valor cifrado em AES-CBC no cofre da sessão.
    Retorna o texto com placeholders e a lista de metadados das entidades mascaradas.
    """
    if not texto or not isinstance(texto, str):
        return texto, []

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")
    analyzer = get_analyzer_engine()
    anonymizer = get_anonymizer_engine()

    try:
        results = analyzer.analyze(text=texto, language="pt")
    except Exception as e:
        logger.warning("Falha ao analisar texto no idioma 'pt': %s", e)
        results = []

    if results:
        results = [
            r for r in results
            if texto[r.start:r.end].strip(" ,.!?:;\"'()[]{}").lower() not in IGNORAR_ENTIDADES
        ]

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

    if not anonymized.items:
        return anonymized.text, []

    cofre_ativo = _resolver_cofre(session_id=session_id, cofre=cofre)
    sorted_items = sorted(anonymized.items, key=lambda x: (x.start, x.end))

    partes: list[str] = []
    itens_saida: list[dict[str, Any]] = []
    cursor = 0
    offset_atual = 0

    for item in sorted_items:
        partes.append(anonymized.text[cursor:item.start])
        offset_atual += item.start - cursor

        aes_token = item.text
        plain_text = AESCipher.decrypt(key=key_bytes, text=aes_token)
        placeholder = cofre_ativo.registrar(
            entity_type=item.entity_type,
            plain_text=plain_text,
            aes_token=aes_token,
            key_bytes=key_bytes,
        )

        inicio_placeholder = offset_atual
        partes.append(placeholder)
        offset_atual += len(placeholder)

        itens_saida.append(
            {
                "start": inicio_placeholder,
                "end": offset_atual,
                "entity_type": item.entity_type,
                "text": placeholder,
                "operator": "placeholder_aes",
            }
        )
        cursor = item.end

    partes.append(anonymized.text[cursor:])
    return "".join(partes), itens_saida


def anonimizar_dados_processo(
    dados: dict[str, Any] | None,
    key: str | None = None,
    session_id: str | None = None,
    cofre: CofreAnonimizacao | None = None,
) -> dict[str, Any] | None:
    """
    Percorre recursivamente a estrutura de dados (dicionário ou lista) e
    anonimiza todos os campos de texto com dados pessoais identificáveis (PII).
    """
    if dados is None:
        return None

    cofre_ativo = _resolver_cofre(session_id=session_id, cofre=cofre)

    def _anonimizar_recursivo(valor: Any) -> Any:
        if isinstance(valor, dict):
            return {k: _anonimizar_recursivo(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [_anonimizar_recursivo(item) for item in valor]
        if isinstance(valor, str):
            texto_anonimizado, _ = anonimizar_texto(
                valor,
                key=key,
                session_id=session_id,
                cofre=cofre_ativo,
            )
            return texto_anonimizado
        return valor

    return _anonimizar_recursivo(dados)


def _restaurar_placeholders(
    texto: str,
    key_bytes: bytes,
    cofre: CofreAnonimizacao,
) -> str:
    """Restaura placeholders curtos (ex: [PESSOA_1]) consultando os tokens AES no cofre."""
    def _substituir(match: re.Match[str]) -> str:
        placeholder = match.group(0)
        aes_token = cofre.obter_token_cifrado(placeholder)
        if aes_token is None:
            return placeholder
        try:
            return AESCipher.decrypt(key=key_bytes, text=aes_token)
        except Exception as e:
            logger.error("Erro ao decifrar placeholder %s do cofre: %s", placeholder, e)
            return placeholder

    return PLACEHOLDER_PATTERN.sub(_substituir, texto)


def _extrair_span_aes_valido(
    token: str,
    start: int,
    end: int,
    key_bytes: bytes,
) -> tuple[int, int] | None:
    """
    Valida se `token` (ou sua subcadeia sem delimitadores `_`/`-` adjacentes, ex: itálico Markdown)
    é decifrável com a chave AES e retorna o intervalo (start, end) correspondente.
    """
    candidatos = [(0, 0)]
    if token.startswith(("_", "-")) and token.endswith(("_", "-")):
        candidatos.append((1, 1))
    if token.startswith(("_", "-")):
        candidatos.append((1, 0))
    if token.endswith(("_", "-")):
        candidatos.append((0, 1))

    for corte_esq, corte_dir in candidatos:
        fim_rel = len(token) - corte_dir
        if fim_rel <= corte_esq:
            continue
        sub = token[corte_esq:fim_rel]
        try:
            AESCipher.decrypt(key=key_bytes, text=sub)
            return start + corte_esq, end - corte_dir
        except Exception:
            continue

    return None


def _restaurar_tokens_aes_diretos(texto: str, encryption_key: str) -> str:
    """Fallback para restaurar tokens AES-CBC presentes diretamente no texto."""
    key_bytes = encryption_key.encode("utf-8")
    matches = list(ENCRYPTED_TOKEN_PATTERN.finditer(texto))
    if not matches:
        return texto

    entities: list[OperatorResult] = []
    for m in matches:
        token = m.group()
        span = _extrair_span_aes_valido(token, m.start(), m.end(), key_bytes)
        if span is not None:
            entities.append(
                OperatorResult(start=span[0], end=span[1], entity_type="ENCRYPTED_PII")
            )
        elif token.endswith("="):
            logger.warning(
                "Candidato a token AES não pôde ser decifrado (possível token alterado): %s...",
                token[:12],
            )

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


def desanonimizar_texto(
    texto: str,
    key: str | None = None,
    session_id: str | None = None,
    cofre: CofreAnonimizacao | None = None,
) -> str:
    """
    Restaura placeholders curtos presentes no texto (via cofre da sessão + AESCipher)
    e mantém compatibilidade com tokens AES-CBC diretos.
    """
    if not texto or not isinstance(texto, str):
        return texto

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")
    cofre_ativo = _resolver_cofre(session_id=session_id, cofre=cofre)

    texto_restaurado = _restaurar_placeholders(texto, key_bytes=key_bytes, cofre=cofre_ativo)
    return _restaurar_tokens_aes_diretos(texto_restaurado, encryption_key=encryption_key)
