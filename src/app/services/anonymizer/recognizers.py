import re
from presidio_analyzer import Pattern, PatternRecognizer


class CpfRecognizer(PatternRecognizer):
    """
    Reconhecedor para CPF (Cadastro de Pessoas Físicas).
    Detecta formatos com e sem pontuação e valida os dígitos verificadores.
    """
    PATTERNS = [
        Pattern(name="cpf_formatado", regex=r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", score=0.85),
        Pattern(name="cpf_apenas_digitos", regex=r"\b\d{11}\b", score=0.4),
    ]
    CONTEXT = ["cpf", "cadastro de pessoa fisica", "documento", "titular", "beneficiario"]

    def __init__(self, supported_language: str = "pt"):
        super().__init__(
            supported_entity="BR_CPF",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """Valida os dígitos verificadores do CPF."""
        digits = [int(c) for c in pattern_text if c.isdigit()]
        if len(digits) != 11 or len(set(digits)) == 1:
            return False

        sum1 = sum(digits[i] * (10 - i) for i in range(9))
        d1 = (sum1 * 10 % 11) % 10
        if d1 != digits[9]:
            return False

        sum2 = sum(digits[i] * (11 - i) for i in range(10))
        d2 = (sum2 * 10 % 11) % 10
        return d2 == digits[10]


class CnpjRecognizer(PatternRecognizer):
    """
    Reconhecedor para CNPJ tradicional e Alfanumérico (IN RFB nº 2.229/2024).
    Suporta:
    - Formato numérico tradicional: 00.000.000/0001-91 ou 00000000000191
    - Formato alfanumérico: 12.ABC.345/01DE-35 ou 12ABC34501DE35
    Valida dígitos verificadores pelo Módulo 11 com tabela ASCII (ord(c) - 48).
    """
    PATTERNS = [
        # Formatado (tradicional ou alfanumérico): XX.XXX.XXX/XXXX-NN
        Pattern(
            name="cnpj_formatado",
            regex=r"(?<![0-9A-Za-z])\b[0-9A-Za-z]{2}\.[0-9A-Za-z]{3}\.[0-9A-Za-z]{3}/[0-9A-Za-z]{4}-\d{2}(?![0-9A-Za-z])\b",
            score=0.85,
        ),
        # Sem formatação (12 alfanuméricos + 2 dígitos numéricos de DV):
        Pattern(
            name="cnpj_sem_formato",
            regex=r"(?<![0-9A-Za-z])\b[0-9A-Za-z]{12}\d{2}(?![0-9A-Za-z])\b",
            score=0.40,
        ),
    ]
    CONTEXT = [
        "cnpj",
        "cadastro nacional da pessoa juridica",
        "empresa",
        "razao social",
        "matriz",
        "filial",
        "inscricao",
        "inscrita",
    ]

    def __init__(self, supported_language: str = "pt"):
        super().__init__(
            supported_entity="BR_CNPJ",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """
        Valida os dígitos verificadores do CNPJ (numérico ou alfanumérico)
        conforme instrução normativa RFB 2.229/2024.
        """
        clean = re.sub(r"[^0-9A-Za-z]", "", pattern_text).upper()
        if len(clean) != 14 or len(set(clean)) == 1:
            return False

        # Os dois últimos caracteres (DV) devem ser estritamente numéricos
        if not (clean[-2].isdigit() and clean[-1].isdigit()):
            return False

        # Regra de conversão ASCII da Receita Federal: valor = ord(c) - 48
        # Ex: '0' -> 0, '9' -> 9, 'A' -> 17, 'Z' -> 42
        vals = [ord(c) - 48 for c in clean]

        # 1º Dígito Verificador (DV1)
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        rem1 = sum(vals[i] * weights1[i] for i in range(12)) % 11
        d1 = 0 if rem1 in (0, 1) else 11 - rem1
        if d1 != int(clean[12]):
            return False

        # 2º Dígito Verificador (DV2)
        vals_with_d1 = vals[:12] + [d1]
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        rem2 = sum(vals_with_d1[i] * weights2[i] for i in range(13)) % 11
        d2 = 0 if rem2 in (0, 1) else 11 - rem2
        return d2 == int(clean[13])


class RgRecognizer(PatternRecognizer):
    """
    Reconhecedor para RG (Registro Geral / Carteira de Identidade).
    Detecta formatos com e sem formatação (incluindo dígito 'X'/'x') e utiliza palavras
    de contexto (como 'rg', 'identidade', 'ssp') para aumentar a precisão e evitar falsos positivos.
    """
    PATTERNS = [
        # Formatado padrão: 12.345.678-9 ou 12.345.678-X (1 ou 2 dígitos no primeiro bloco)
        Pattern(
            name="rg_formatado_padrao",
            regex=r"(?<!\d)\b\d{1,2}\.\d{3}\.\d{3}-[\dXx](?![\dXx])\b",
            score=0.85,
        ),
        # Formatado sem hífen: 12.345.678 (o lookahead negativo ?![\\d/] evita colisão com CNPJ)
        Pattern(
            name="rg_formatado_sem_hifen",
            regex=r"(?<!\d)\b\d{1,2}\.\d{3}\.\d{3}(?![\d/])\b",
            score=0.60,
        ),
        # Sem formatação (7 a 8 dígitos + dígito ou X): ex: 123456789 ou 12345678X
        # Score inicial baixo (0.35) que é ampliado quando palavras de contexto estão próximas
        Pattern(
            name="rg_sem_formato",
            regex=r"(?<!\d)\b\d{7,8}[\dXx](?![\dXx])\b",
            score=0.35,
        ),
    ]

    CONTEXT = [
        "rg",
        "identidade",
        "registro geral",
        "cedula de identidade",
        "carteira de identidade",
        "ssp",
        "detran",
        "expedicao",
        "emissor",
        "documento",
    ]

    def __init__(self, supported_language: str = "pt"):
        super().__init__(
            supported_entity="BR_RG",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """Descarta sequências inválidas, como dígitos todos repetidos."""
        clean = "".join(c for c in pattern_text if c.isalnum())
        if len(set(clean)) == 1:
            return False
        return True


class BrazilPhoneRecognizer(PatternRecognizer):
    """
    Reconhecedor para números de telefone brasileiros (Celular e Fixo),
    com e sem formatação (ex: 11903030303, (11) 90303-0303, 1103030303, (11) 0303-0303, 0800, etc.).
    """
    PATTERNS = [
        # 1. Celular formatado: (11) 90303-0303, +55 (11) 90303-0303, 11 90303-0303
        Pattern(
            name="br_phone_celular_formatado",
            regex=r"(?<!\d)(?:\+?55\s?)?(?:\([1-9][0-9]\)\s?|[1-9][0-9]\s?)9\s?\d{4}[-\s]?\d{4}(?!\d)",
            score=0.85,
        ),
        # 2. Telefone fixo formatado: (11) 0303-0303, (11) 3232-4040, 11 0303-0303
        Pattern(
            name="br_phone_fixo_formatado",
            regex=r"(?<!\d)(?:\+?55\s?)?(?:\([1-9][0-9]\)\s?|[1-9][0-9]\s?)[0-9]\d{3}[-\s]?\d{4}(?!\d)",
            score=0.85,
        ),
        # 3. Número local com hífen (sem DDD): 90303-0303, 0303-0303, 3232-4040
        Pattern(
            name="br_phone_local_formatado",
            regex=r"(?<!\d)(?:9\s?\d{4}|[0-9]\d{3})[-\s]\d{4}(?!\d)",
            score=0.75,
        ),
        # 4. Números 0800 e 0300: 0800 707 0100, 0800-707-0100, 08007070100
        Pattern(
            name="br_phone_0800",
            regex=r"(?<!\d)0[38]00[-\s]?\d{3}[-\s]?\d{4}(?!\d)",
            score=0.85,
        ),
        # 5. Celular sem formatação (11 dígitos): ex: 11903030303 ou 5511903030303
        Pattern(
            name="br_phone_celular_sem_formato",
            regex=r"(?<!\d)(?:\+?55)?[1-9][0-9]9\d{8}(?!\d)",
            score=0.70,
        ),
        # 6. Telefone fixo sem formatação (10 dígitos): ex: 1103030303, 1132324040 ou 551103030303
        Pattern(
            name="br_phone_fixo_sem_formato",
            regex=r"(?<!\d)(?:\+?55)?[1-9][0-9][0-9]\d{7}(?!\d)",
            score=0.70,
        ),
    ]

    CONTEXT = [
        "telefone",
        "celular",
        "tel",
        "contato",
        "whatsapp",
        "whats",
        "fone",
        "fixo",
        "ligar",
        "chamar",
        "ramal",
        "phone",
    ]

    def __init__(self, supported_language: str = "pt"):
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )


class RazaoSocialRecognizer(PatternRecognizer):
    """
    Reconhecedor para Razão Social / Nome Empresarial brasileiro.
    Detecta a estrutura corporativa através dos tipos societários (LTDA, S.A., EIRELI, ME, EPP, etc.)
    e evita falsos positivos gerados por classificações genéricas de 'PERSON' do spaCy.
    """
    LEGAL_SUFFIXES = (
        r"(?:LTDA\.?|Ltda\.?|LIMITADA|Limitada|"
        r"S\.?A\.?|S/A|EIRELI|Eireli|M\.?E\.?|ME|E\.?P\.?P\.?|EPP|"
        r"MEI|Mei|S/?S|SPE|CIA\.?|Cia\.?|COMPANHIA|Companhia|HOLDING|Holding)"
    )
    WORD = r"(?:[A-ZÀ-Ú][a-zà-ú0-9]+|[A-ZÀ-Ú0-9]{2,})"
    CONNECTOR = r"(?:de|da|do|dos|das|e|em|para|com|&|\-)"
    START_IGNORE = r"(?!Contrato\b|Empresa\b|Fornecedor\b|Cliente\b|Entre\b|Pela\b|Pelo\b|Com\b)"

    PATTERNS = [
        # Razão social com tipo societário obrigatório (ex: Silva & Souza Transportes Ltda., Acme S.A.)
        Pattern(
            name="razao_social_sufixo",
            regex=rf"\b{START_IGNORE}{WORD}(?:\s+(?:{WORD}|{CONNECTOR})){{1,8}}\s+{LEGAL_SUFFIXES}(?!\w)",
            score=0.90,
        ),
    ]

    CONTEXT = [
        "razao social",
        "empresa",
        "nome empresarial",
        "fornecedor",
        "contratada",
        "contratante",
        "sociedade",
        "cnpj",
        "pj",
        "pessoa juridica",
    ]

    def __init__(self, supported_language: str = "pt"):
        super().__init__(
            supported_entity="BR_RAZAO_SOCIAL",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )


class CnjRecognizer(PatternRecognizer):
    """
    Reconhecedor para Número Único de Processo Judicial (Padrão CNJ - Resolução 65/2008).
    Formato: NNNNNNN-DD.AAAA.J.TR.OOOO (20 dígitos).
    Inclui validação matemática pelo algoritmo Módulo 97 (ISO 7064).
    """
    PATTERNS = [
        # Formatado padrão: 0000001-84.2020.8.26.0001
        Pattern(
            name="cnj_formatado",
            regex=r"(?<!\d)\b\d{7}-\d{2}\.\d{4}\.[1-9]\.\d{2}\.\d{4}\b",
            score=0.90,
        ),
        # Sem formatação: 20 dígitos diretos
        Pattern(
            name="cnj_sem_formato",
            regex=r"(?<!\d)\b\d{13}[1-9]\d{6}(?!\d)",
            score=0.40,
        ),
    ]

    CONTEXT = [
        "processo",
        "cnj",
        "autos",
        "acao",
        "ação",
        "juizo",
        "juízo",
        "vara",
        "comarca",
        "tribunal",
        "recurso",
        "distribuicao",
        "distribuição",
        "mandado",
        "intimacao",
        "intimação",
        "citacao",
        "citação",
        "processual",
    ]

    def __init__(self, supported_language: str = "pt"):
        super().__init__(
            supported_entity="BR_CNJ",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """Valida o número do processo pelo cálculo do Módulo 97 (ISO 7064) da Resolução 65 do CNJ."""
        digits = "".join(c for c in pattern_text if c.isdigit())
        if len(digits) != 20:
            return False

        # Fatiamento: NNNNNNN (7) DD (2) AAAA (4) J (1) TR (2) OOOO (4)
        n7 = digits[:7]
        dd = digits[7:9]
        aaaa = digits[9:13]
        j = digits[13:14]
        tr = digits[14:16]
        oooo = digits[16:20]

        # J identifica o segmento da Justiça (1 a 9):
        # 1-STF, 2-CNJ, 3-STJ, 4-Federal, 5-Trabalho, 6-Eleitoral, 7-Militar União, 8-Estadual, 9-Militar Estadual
        if not (1 <= int(j) <= 9):
            return False

        # Validação Módulo 97 (ISO 7064):
        # A concatenação NNNNNNNAAAAJTROOOODD % 97 deve ser rigorosamente igual a 1
        num = int(f"{n7}{aaaa}{j}{tr}{oooo}{dd}")
        return num % 97 == 1
