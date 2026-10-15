import logging
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine, DeanonymizeEngine

from src.app.services.anonymizer.recognizers import (
    BrazilPhoneRecognizer,
    CnjRecognizer,
    CnpjRecognizer,
    CpfRecognizer,
    RazaoSocialRecognizer,
    RgRecognizer,
)

logger = logging.getLogger(__name__)

_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None
_deanonymizer: DeanonymizeEngine | None = None


def _init_engines() -> tuple[AnalyzerEngine, AnonymizerEngine, DeanonymizeEngine]:
    """Inicializa os motores do Presidio configurando o modelo de linguagem e reconhecedores personalizados."""
    global _analyzer, _anonymizer, _deanonymizer

    if _analyzer is not None and _anonymizer is not None and _deanonymizer is not None:
        return _analyzer, _anonymizer, _deanonymizer

    # Configuração do spaCy para suportar português e inglês
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "pt", "model_name": "pt_core_news_sm"},
            {"lang_code": "en", "model_name": "en_core_web_lg"},
        ],
    }

    try:
        provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
        nlp_engine = provider.create_engine()
        analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["pt", "en"])
    except Exception as e:
        logger.warning(
            "Falha ao carregar modelos spaCy multilíngues (%s). Usando configuração padrão do AnalyzerEngine.",
            e,
        )
        analyzer = AnalyzerEngine()

    # Registro dos reconhecedores personalizados para 'pt' e 'en'
    for lang in ["pt", "en"]:
        analyzer.registry.add_recognizer(CpfRecognizer(supported_language=lang))
        analyzer.registry.add_recognizer(CnpjRecognizer(supported_language=lang))
        analyzer.registry.add_recognizer(RgRecognizer(supported_language=lang))
        analyzer.registry.add_recognizer(BrazilPhoneRecognizer(supported_language=lang))
        analyzer.registry.add_recognizer(RazaoSocialRecognizer(supported_language=lang))
        analyzer.registry.add_recognizer(CnjRecognizer(supported_language=lang))

    anonymizer = AnonymizerEngine()
    deanonymizer = DeanonymizeEngine()

    _analyzer = analyzer
    _anonymizer = anonymizer
    _deanonymizer = deanonymizer

    return _analyzer, _anonymizer, _deanonymizer


def get_analyzer_engine() -> AnalyzerEngine:
    analyzer, _, _ = _init_engines()
    return analyzer


def get_anonymizer_engine() -> AnonymizerEngine:
    _, anonymizer, _ = _init_engines()
    return anonymizer


def get_deanonymize_engine() -> DeanonymizeEngine:
    _, _, deanonymizer = _init_engines()
    return deanonymizer
