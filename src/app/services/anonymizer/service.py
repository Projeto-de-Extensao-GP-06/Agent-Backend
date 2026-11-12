from collections.abc import Sequence
import logging
import re
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

# Padrão de regex para identificar tokens criptografados com AESCipher (Base64 URL-safe >= 43 chars)
ENCRYPTED_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43,}={0,2}")

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


def _cifrar_com_mapa(
    texto: str,
    key_bytes: bytes,
    mapa_tokens: dict[str, str] | None = None,
) -> str:
    """Cifra um texto com AES-CBC, reutilizando o token se o mesmo valor já tiver sido cifrado no mapa."""
    texto_limpo = texto.strip()
    if not texto_limpo:
        return texto

    if _is_encrypted_token(texto_limpo, key_bytes):
        return texto_limpo

    chave_mapa = texto_limpo.lower()
    if mapa_tokens is not None and chave_mapa in mapa_tokens:
        return mapa_tokens[chave_mapa]

    token = AESCipher.encrypt(key=key_bytes, text=texto_limpo)
    if mapa_tokens is not None:
        mapa_tokens[chave_mapa] = token
    return token


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
) -> tuple[str, list[dict[str, Any]]]:
    """
    Analisa e anonimiza o texto utilizando criptografia reversível AES.
    Limita a detecção apenas a entidades estruturadas/validadas (CPF, CNPJ, RG, Telefone, E-mail,
    CNJ, Razão Social) e aos termos sensíveis conhecidos do processo (`termos_conhecidos`),
    evitando que siglas (como 'LGPD', 'TJSP', 'SAJ') ou palavras comuns sejam censuradas.
    """
    if not texto or not isinstance(texto, str):
        return texto, []

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")

    if _is_encrypted_token(texto, key_bytes):
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
            trecho = texto[r.start : r.end]
            trecho_normalizado = trecho.strip(" ,.!?:;\"'()[]{}").lower()
            if trecho_normalizado in IGNORAR_ENTIDADES:
                continue
            if _is_encrypted_token(trecho, key_bytes):
                continue
            results_filtrados.append(r)
        results = results_filtrados

    if not results:
        return texto, []

    operators = {
        "DEFAULT": OperatorConfig(
            "custom",
            {"lambda": lambda span_text: _cifrar_com_mapa(span_text, key_bytes, mapa_tokens)},
        )
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
            "operator": "encrypt",
        }
        for item in anonymized.items
    ]

    return anonymized.text, items


def anonimizar_dados_processo(
    dados: dict[str, Any] | None,
    key: str | None = None,
    mapa_tokens: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """
    Anonimiza seletivamente a estrutura `dados_processo` de acordo com o schema do SGPJ:
    - Cifra integralmente campos de identificação das partes e do processo (ex: `clientNomeRazaoSocial`,
      `clienteId`, `usuarioResponsavelNome`, `usuarioResponsavelId`, `numeroCnj`, autor em `historicoProcessoResponses`).
    - Analisa via Presidio apenas os campos de texto livre (`descricaoCaso`, `obervacao`/`observacao`, `ultimoMovimento`).
    - Preserva intactos os metadados de sistema/tribunal (`prioridade`, `faseProcesso`, `status`, `siglaTribunal`,
      `sistemaTribunal`, `classeProcessual`, `assunto`, `orgaoJulgador`, datas e `valorCausa`).
    """
    if dados is None:
        return None

    encryption_key = key or settings.anonymization_key
    key_bytes = encryption_key.encode("utf-8")
    tokens_cache: dict[str, str] = mapa_tokens if mapa_tokens is not None else {}

    # 1. Extrai previamente os nomes/termos sensíveis do próprio processo
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

        # 4. Campos de identificação direta (clientNomeRazaoSocial, clienteId, usuarioResponsavelNome, usuarioResponsavelId, numeroCnj, etc.)
        if _eh_campo_cifrar_direto(chave_norm, pai_norm):
            if valor is None or isinstance(valor, bool):
                return valor
            if isinstance(valor, (str, int)):
                texto_val = str(valor).strip()
                if not texto_val:
                    return valor
                return _cifrar_com_mapa(texto_val, key_bytes, tokens_cache)
            return valor

        # 5. Campos de texto livre (descricaoCaso, obervacao, ultimoMovimento, etc.)
        if isinstance(valor, str):
            texto_anonimizado, _ = anonimizar_texto(
                valor,
                key=encryption_key,
                termos_conhecidos=termos_conhecidos,
                mapa_tokens=tokens_cache,
            )
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
