from collections.abc import Sequence
import hashlib
import hmac
import logging
import re
from threading import Lock
from typing import Any

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
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
    "SISTEMA_PII": "ENTIDADE",
}

# Entidades determinísticas/estruturadas ativas por padrão (desativa o NER aberto do spaCy
# como PERSON, LOCATION, NRP e DATE_TIME para evitar falsos positivos em siglas como "LGPD", "TJSP", "SAJ")
ENTIDADES_PADRAO_SISTEMA: list[str] = [
    "BR_CPF",
    "BR_CNPJ",
    "BR_RG",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "BR_CNJ",
    "BR_RAZAO_SOCIAL",
]

# Campos de dados_processo cujo valor inteiro deve ser cifrado diretamente (Identificação, Partes e CNJ)
CAMPOS_CIFRAR_DIRETO: set[str] = {
    # Schema oficial SGPJ - Identificação, Partes e Dados Técnicos Sensíveis
    "clientnomerazaosocial",
    "clientenomerazaosocial",
    "clienteid",
    "usuarioresponsavelnome",
    "usuarioresponsavelid",
    "numerocnj",
    # Histórico (historicoProcessoResponses - quem alterou)
    "usuarionome",
    "usuarioid",
    "nomeusuario",
    "alteradopor",
    "alteradoporid",
    "alteradopornome",
    "modificadopor",
    "criadopor",
    "responsavel",
    "responsavelid",
    "responsavelnome",
    "autor",
    "autorid",
    "autornome",
    # Retrocompatibilidade com estruturas auxiliares e testes
    "cpf",
    "cnpj",
    "rg",
    "telefone",
    "celular",
    "email",
    "processocnj",
    "empresa",
    "reclamado",
    "processo",
}

# Campos que identificam objetos de partes/usuários (onde subcampos 'nome', 'id', 'razaoSocial' são PII)
CONTEXTOS_PARTE_SENSIVEL: set[str] = {
    "cliente",
    "usuario",
    "usuarioresponsavel",
    "responsavel",
    "alteradopor",
    "autor",
    "reu",
    "parte",
}

# Subcampos sensíveis quando dentro de um objeto em CONTEXTOS_PARTE_SENSIVEL
SUBCAMPOS_PARTE_SENSIVEL: set[str] = {
    "nome",
    "id",
    "razaosocial",
    "nomerazaosocial",
}

# Campos cujos valores textuais (nomes/razões sociais/documentos) devem alimentar o reconhecedor dinâmico
# para serem censurados também caso apareçam em campos de texto livre ou na mensagem do usuário
CAMPOS_FONTE_TERMOS_CONHECIDOS: set[str] = {
    "clientnomerazaosocial",
    "clientenomerazaosocial",
    "usuarioresponsavelnome",
    "usuarionome",
    "nomeusuario",
    "alteradopor",
    "alteradopornome",
    "modificadopor",
    "criadopor",
    "responsavel",
    "responsavelnome",
    "autor",
    "autornome",
    "numerocnj",
    "processocnj",
    "processo",
    "empresa",
    "reclamado",
    "cpf",
    "cnpj",
    "rg",
    "telefone",
    "celular",
    "email",
}

# Campos de texto livre onde o Presidio deve procurar PII (CPF, CNPJ, RG, Telefone, E-mail, CNJ, Razão Social e nomes das partes)
CAMPOS_TEXTO_LIVRE: set[str] = {
    "descricaocaso",
    "obervacao",
    "observacao",
    "ultimomovimento",
    "resumo",
    "descricao",
    "detalhe",
    "detalhes",
    "comentario",
    "mensagem",
}

# Campos de metadados do sistema/tribunal que NUNCA devem ser censurados
CAMPOS_PRESERVADOS: set[str] = {
    "valorcausa",
    "prioridade",
    "faseprocesso",
    "status",
    "dataaudiencia",
    "datahorainicio",
    "ultimaatualizacao",
    "siglatribunal",
    "tribunaltramitacao",
    "instancia",
    "dataajuizamento",
    "nivelsigilo",
    "classeprocessual",
    "formato",
    "sistematribunal",
    "orgaojulgador",
    "assunto",
    # Metadados de histórico (quando e tipo de atualização)
    "data",
    "datahora",
    "quando",
    "dataalteracao",
    "dataatualizacao",
    "criadoem",
    "tipo",
    "tipoatualizacao",
    "tipoalteracao",
    "acao",
    "evento",
    "campo",
    "campoalterado",
    # Atributos estruturais
    "ativo",
    "peso",
    "ordem",
    "sigla",
}

# Deny-list complementar de segurança
IGNORAR_ENTIDADES: set[str] = {
    "lgpd",
    "sgpj",
    "saj",
    "pje",
    "eproc",
    "projudi",
    "stf",
    "stj",
    "tst",
    "cnj",
    "oab",
    "olá",
    "ola",
    "oi",
    "bom dia",
    "boa tarde",
    "boa noite",
    "por favor",
    "obrigado",
    "obrigada",
}


def _normalizar_chave(chave: str) -> str:
    """Normaliza o nome de uma chave JSON removendo caracteres especiais e convertendo para minúsculas."""
    return re.sub(r"[^a-z0-9]", "", chave.lower())


def _obter_prefixo_entidade(entity_type: str) -> str:
    """Converte o tipo de entidade do Presidio em um prefixo curto para placeholder."""
    prefixo = ENTITY_PREFIX_MAP.get(entity_type)
    if prefixo:
        return prefixo
    normalizado = re.sub(r"[^A-Z0-9_]", "_", entity_type.upper()).strip("_")
    return normalizado or "DADO"


def _obter_prefixo_campo(chave_norm: str) -> str:
    """Define um prefixo semântico curto para campos cifrados diretamente pelo schema."""
    if "cpf" in chave_norm:
        return "CPF"
    if "cnpj" in chave_norm:
        return "CNPJ"
    if chave_norm == "rg":
        return "RG"
    if "telefone" in chave_norm or "celular" in chave_norm:
        return "TELEFONE"
    if "email" in chave_norm:
        return "EMAIL"
    if "cnj" in chave_norm or "processo" in chave_norm:
        return "PROCESSO_CNJ"
    if "empresa" in chave_norm or "reclamado" in chave_norm:
        return "EMPRESA"
    if chave_norm.endswith("id") or chave_norm == "id":
        return "ID"
    if any(
        termo in chave_norm
        for termo in ("nome", "razao", "responsavel", "usuario", "autor", "alteradopor", "modificadopor", "criadopor")
    ):
        return "PESSOA"
    return "DADO"


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

    @staticmethod
    def _calcular_hash_dedup(plain_text: str, key_bytes: bytes) -> str:
        normalizado = plain_text.strip().lower().encode("utf-8")
        return hmac.new(key_bytes, normalizado, hashlib.sha256).hexdigest()

    def obter_existente(self, plain_text: str, key_bytes: bytes) -> str | None:
        """Retorna placeholder já registrado para o mesmo valor nesta sessão, se houver."""
        dedup_key = self._calcular_hash_dedup(plain_text, key_bytes)
        with self._lock:
            return self._hash_to_placeholder.get(dedup_key)

    def registrar(
        self,
        entity_type: str,
        plain_text: str,
        aes_token: str,
        key_bytes: bytes,
        prefixo_override: str | None = None,
    ) -> str:
        """Registra (ou reutiliza) um placeholder curto para uma entidade cifrada."""
        prefixo = prefixo_override or _obter_prefixo_entidade(entity_type)
        dedup_key = self._calcular_hash_dedup(plain_text, key_bytes)

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


def _is_encrypted_token(texto: str, key_bytes: bytes) -> bool:
    """Verifica se uma string já é um token AES válido gerado por esta chave."""
    texto_limpo = texto.strip()
    if not ENCRYPTED_TOKEN_PATTERN.fullmatch(texto_limpo):
        return False
    try:
        AESCipher.decrypt(key=key_bytes, text=texto_limpo)
        return True
    except Exception:
        return False


def _is_placeholder(texto: str, cofre: CofreAnonimizacao) -> bool:
    """Verifica se uma string já é um placeholder registrado no cofre ativo."""
    texto_limpo = texto.strip()
    return (
        bool(PLACEHOLDER_PATTERN.fullmatch(texto_limpo))
        and cofre.obter_token_cifrado(texto_limpo) is not None
    )


def _cifrar_com_cofre(
    texto: str,
    key_bytes: bytes,
    cofre: CofreAnonimizacao,
    prefixo: str = "DADO",
    mapa_tokens: dict[str, str] | None = None,
) -> str:
    """Cifra um texto com AES-CBC, registra no cofre e retorna um placeholder curto reutilizável."""
    texto_limpo = texto.strip()
    if not texto_limpo:
        return texto

    if _is_placeholder(texto_limpo, cofre) or _is_encrypted_token(texto_limpo, key_bytes):
        return texto_limpo

    existente = cofre.obter_existente(texto_limpo, key_bytes)
    if existente is not None:
        if mapa_tokens is not None:
            mapa_tokens[texto_limpo.lower()] = existente
        return existente

    token = AESCipher.encrypt(key=key_bytes, text=texto_limpo)
    placeholder = cofre.registrar(
        entity_type=prefixo,
        plain_text=texto_limpo,
        aes_token=token,
        key_bytes=key_bytes,
        prefixo_override=prefixo,
    )
    if mapa_tokens is not None:
        mapa_tokens[texto_limpo.lower()] = placeholder
    return placeholder


def _criar_reconhecedor_termos_sistema(termos: Sequence[str]) -> PatternRecognizer | None:
    """
    Cria um PatternRecognizer dinâmico (ad-hoc) com os valores sensíveis reais extraídos
    do processo (como clientNomeRazaoSocial e usuarioResponsavelNome).
    """
    termos_unicos: list[str] = []
    vistos: set[str] = set()

    for termo in termos:
        if not isinstance(termo, str):
            continue
        limpo = termo.strip()
        if len(limpo) < 3:
            continue
        # Evita adicionar números puros curtos (ex: IDs numéricos simples) como regex de texto livre
        if limpo.isdigit() and len(limpo) < 7:
            continue
        chave = limpo.lower()
        if chave not in vistos and chave not in IGNORAR_ENTIDADES:
            vistos.add(chave)
            termos_unicos.append(limpo)

    if not termos_unicos:
        return None

    # Ordena do maior para o menor para priorizar nomes completos sobre substrings
    termos_unicos.sort(key=len, reverse=True)

    patterns = [
        Pattern(
            name=f"termo_sistema_{idx}",
            regex=rf"(?i)(?<!\w){re.escape(termo)}(?!\w)",
            score=1.0,
        )
        for idx, termo in enumerate(termos_unicos)
    ]

    return PatternRecognizer(
        supported_entity="SISTEMA_PII",
        name="SistemaDadosProcessoRecognizer",
        patterns=patterns,
        supported_language="pt",
    )


def extrair_termos_sensiveis_processo(dados: dict[str, Any] | None) -> list[str]:
    """
    Extrai os nomes e identificadores textuais sensíveis presentes em `dados_processo`
    para que também sejam reconhecidos em campos de texto livre e na mensagem do usuário.
    """
    if not dados or not isinstance(dados, dict):
        return []

    termos: list[str] = []

    def _coletar(valor: Any, chave_atual: str = "", contexto_pai: str = "") -> None:
        chave_norm = _normalizar_chave(chave_atual) if chave_atual else ""
        pai_norm = _normalizar_chave(contexto_pai) if contexto_pai else ""

        if chave_norm in CAMPOS_PRESERVADOS:
            return

        if isinstance(valor, dict):
            novo_contexto = chave_norm if chave_norm in CONTEXTOS_PARTE_SENSIVEL else pai_norm
            for k, v in valor.items():
                _coletar(v, chave_atual=str(k), contexto_pai=novo_contexto)
            return

        if isinstance(valor, list):
            for item in valor:
                _coletar(item, chave_atual=chave_atual, contexto_pai=pai_norm)
            return

        if isinstance(valor, str):
            texto = valor.strip()
            if not texto:
                return
            eh_fonte_direta = chave_norm in CAMPOS_FONTE_TERMOS_CONHECIDOS
            eh_nome_parte = pai_norm in CONTEXTOS_PARTE_SENSIVEL and chave_norm in {"nome", "razaosocial", "nomerazaosocial"}
            eh_usuario_historico = pai_norm == "historicoprocessoresponses" and chave_norm == "usuario"
            if eh_fonte_direta or eh_nome_parte or eh_usuario_historico:
                termos.append(texto)

    _coletar(dados)
    return termos


def anonimizar_texto(
    texto: str,
    key: str | None = None,
    termos_conhecidos: Sequence[str] | None = None,
    mapa_tokens: dict[str, str] | None = None,
    session_id: str | None = None,
    cofre: CofreAnonimizacao | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Analisa e anonimiza o texto substituindo PII por placeholders curtos (ex: [PESSOA_1], [CPF_1])
    e armazenando o respectivo valor cifrado em AES-CBC no cofre da sessão.
    Limita a detecção a entidades estruturadas/validadas (CPF, CNPJ, RG, Telefone, E-mail,
    CNJ, Razão Social) e aos termos sensíveis conhecidos do processo (`termos_conhecidos`),
    evitando que siglas (como 'LGPD', 'TJSP', 'SAJ') ou palavras comuns sejam censuradas.
    """
    if not texto or not isinstance(texto, str):
        return texto, []

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")
    cofre_ativo = _resolver_cofre(session_id=session_id, cofre=cofre)

    if _is_placeholder(texto, cofre_ativo) or _is_encrypted_token(texto, key_bytes):
        return texto, []

    analyzer = get_analyzer_engine()
    anonymizer = get_anonymizer_engine()

    entidades_busca = list(ENTIDADES_PADRAO_SISTEMA)
    ad_hoc_recognizers: list[PatternRecognizer] = []

    if termos_conhecidos:
        rec_sistema = _criar_reconhecedor_termos_sistema(termos_conhecidos)
        if rec_sistema is not None:
            ad_hoc_recognizers.append(rec_sistema)
            entidades_busca.append("SISTEMA_PII")

    try:
        results = analyzer.analyze(
            text=texto,
            language="pt",
            entities=entidades_busca,
            ad_hoc_recognizers=ad_hoc_recognizers or None,
        )
    except Exception as e:
        logger.warning("Falha ao analisar texto no idioma 'pt': %s", e)
        results = []

    if results:
        results_filtrados: list[RecognizerResult] = []
        for r in results:
            trecho = texto[r.start:r.end]
            trecho_normalizado = trecho.strip(" ,.!?:;\"'()[]{}").lower()
            if trecho_normalizado in IGNORAR_ENTIDADES:
                continue
            if _is_placeholder(trecho, cofre_ativo) or _is_encrypted_token(trecho, key_bytes):
                continue
            results_filtrados.append(r)
        results = results_filtrados

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
        if mapa_tokens is not None:
            mapa_tokens[plain_text.strip().lower()] = placeholder

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
    mapa_tokens: dict[str, str] | None = None,
    session_id: str | None = None,
    cofre: CofreAnonimizacao | None = None,
) -> dict[str, Any] | None:
    """
    Anonimiza seletivamente a estrutura `dados_processo` de acordo com o schema do SGPJ:
    - Cifra e substitui por placeholders curtos campos de identificação das partes e do processo
      (ex: `clientNomeRazaoSocial`, `clienteId`, `usuarioResponsavelNome`, `usuarioResponsavelId`,
      `numeroCnj`, autor em `historicoProcessoResponses`).
    - Analisa via Presidio apenas os campos de texto livre (`descricaoCaso`, `obervacao`/`observacao`, `ultimoMovimento`).
    - Preserva intactos os metadados de sistema/tribunal (`prioridade`, `faseProcesso`, `status`, `siglaTribunal`,
      `sistemaTribunal`, `classeProcessual`, `assunto`, `orgaoJulgador`, datas e `valorCausa`).
    """
    if dados is None:
        return None

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")
    cofre_ativo = _resolver_cofre(session_id=session_id, cofre=cofre)
    termos_conhecidos = extrair_termos_sensiveis_processo(dados)

    def _eh_campo_cifrar_direto(chave_norm: str, pai_norm: str) -> bool:
        if chave_norm in CAMPOS_CIFRAR_DIRETO:
            return True
        if pai_norm in CONTEXTOS_PARTE_SENSIVEL and chave_norm in SUBCAMPOS_PARTE_SENSIVEL:
            return True
        if pai_norm == "historicoprocessoresponses" and chave_norm == "usuario":
            return True
        return False

    def _anonimizar_recursivo(valor: Any, chave_atual: str = "", contexto_pai: str = "") -> Any:
        chave_norm = _normalizar_chave(chave_atual) if chave_atual else ""
        pai_norm = _normalizar_chave(contexto_pai) if contexto_pai else ""

        # 1. Metadados do sistema/tribunal/datas/valores nunca são censurados
        if chave_norm in CAMPOS_PRESERVADOS:
            return valor

        # 2. Dicionários aninhados
        if isinstance(valor, dict):
            novo_contexto = (
                chave_norm
                if (chave_norm in CONTEXTOS_PARTE_SENSIVEL or chave_norm == "historicoprocessoresponses")
                else pai_norm
            )
            return {
                k: _anonimizar_recursivo(v, chave_atual=str(k), contexto_pai=novo_contexto)
                for k, v in valor.items()
            }

        # 3. Listas (ex: historicoProcessoResponses)
        if isinstance(valor, list):
            novo_contexto = "historicoprocessoresponses" if chave_norm == "historicoprocessoresponses" else pai_norm
            return [
                _anonimizar_recursivo(item, chave_atual=chave_atual, contexto_pai=novo_contexto)
                for item in valor
            ]

        # 4. Campos de identificação direta
        if _eh_campo_cifrar_direto(chave_norm, pai_norm):
            if valor is None or isinstance(valor, bool):
                return valor
            if isinstance(valor, (str, int)):
                texto_val = str(valor).strip()
                if not texto_val:
                    return valor
                return _cifrar_com_cofre(
                    texto_val,
                    key_bytes=key_bytes,
                    cofre=cofre_ativo,
                    prefixo=_obter_prefixo_campo(chave_norm),
                    mapa_tokens=mapa_tokens,
                )
            return valor

        # 5. Campos de texto livre
        if isinstance(valor, str):
            texto_anonimizado, _ = anonimizar_texto(
                valor,
                key=encryption_key,
                termos_conhecidos=termos_conhecidos,
                mapa_tokens=mapa_tokens,
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
