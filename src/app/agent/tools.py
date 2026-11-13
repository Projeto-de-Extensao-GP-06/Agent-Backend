import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from langchain.tools import tool
from pydantic import BaseModel, Field

from src.app.services.anonymizer import desanonimizar_texto

_LEMBRETE_PATTERN = re.compile(r"^-P(?:\d+[WD]|T(?:\d+[HMS])+)$")


@tool
def testeTool() -> str:
    """Retorna uma string específica para testar funcionamento da tool"""
    return "Teste health check tool"


class GerarEventoIcsInput(BaseModel):
    """Parâmetros de entrada validados para geração de arquivo de calendário .ics."""

    titulo: str = Field(..., description="Título do compromisso ou audiência (obrigatório).")
    data_inicio: str = Field(..., description="Data de início no formato YYYY-MM-DD (obrigatório).")
    dia_inteiro: bool = Field(
        ...,
        description="Indica se o evento dura o dia inteiro (true) ou possui horário marcado (false).",
    )
    hora_inicio: str | None = Field(
        default=None,
        description="Horário de início no formato HH:MM. Obrigatório quando dia_inteiro=false.",
    )
    hora_fim: str | None = Field(
        default=None,
        description="Horário de término no formato HH:MM. Obrigatório quando dia_inteiro=false.",
    )
    data_termino: str | None = Field(
        default=None,
        description="Data de término no formato YYYY-MM-DD. Opcional; se omitida, assume data_inicio.",
    )
    descricao: str | None = Field(
        default=None,
        description="Descrição, pauta ou observações do compromisso (opcional).",
    )
    local: str | None = Field(
        default=None,
        description="Endereço físico ou link da sala virtual (opcional).",
    )
    lembrete: str | None = Field(
        default=None,
        description=(
            "Antecedência do lembrete em duração ISO 8601 negativa (ex: -PT15M, -PT30M, "
            "-PT1H, -PT2H, -P1D, -P2D, -P1W). Informar apenas quando solicitado pelo usuário."
        ),
    )


def _parse_iso_date(valor: str, nome_campo: str) -> date:
    try:
        return datetime.strptime(valor.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"O campo '{nome_campo}' deve estar no formato YYYY-MM-DD válido.") from exc


def _parse_hhmm_time(valor: str | None, nome_campo: str) -> time:
    if not valor or not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"O campo '{nome_campo}' é obrigatório para eventos com horário definido.")
    try:
        return datetime.strptime(valor.strip(), "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"O campo '{nome_campo}' deve estar no formato HH:MM válido (00:00 a 23:59).") from exc


def _escapar_texto_ics(texto: str | None) -> str:
    if not texto:
        return ""
    return (
        texto.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _slugificar_nome_arquivo(titulo: str, data_inicio: str) -> str:
    normalizado = unicodedata.normalize("NFD", titulo or "evento")
    sem_acentos = "".join(ch for ch in normalizado if unicodedata.category(ch) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acentos.lower()).strip("-")
    if not slug:
        slug = "evento"
    return f"{slug}-{data_inicio}.ics"


def compilar_anexo_ics(dados_evento: dict[str, Any]) -> dict[str, str]:
    """
    Desanonimiza os campos textuais do evento e gera o conteúdo completo no padrão RFC 5545 (.ics),
    seguindo a especificação do SGPJ.
    """
    titulo = str(desanonimizar_texto(str(dados_evento.get("titulo") or "Compromisso Jurídico"))).strip()
    descricao_raw = dados_evento.get("descricao")
    descricao = str(desanonimizar_texto(str(descricao_raw))).strip() if descricao_raw else ""
    local_raw = dados_evento.get("local")
    local = str(desanonimizar_texto(str(local_raw))).strip() if local_raw else ""

    data_inicio_str = str(dados_evento["data_inicio"])
    data_termino_str = str(dados_evento.get("data_termino") or data_inicio_str)
    dia_inteiro = bool(dados_evento.get("dia_inteiro"))
    lembrete = dados_evento.get("lembrete")

    agora_utc = datetime.now(timezone.utc)
    dtstamp = agora_utc.strftime("%Y%m%dT%H%M%SZ")
    uid = f"{int(agora_utc.timestamp() * 1000)}-{uuid4().hex[:7]}@sgpj.adv.br"

    data_inicio_obj = _parse_iso_date(data_inicio_str, "data_inicio")
    data_termino_obj = _parse_iso_date(data_termino_str, "data_termino")

    if dia_inteiro:
        dtstart_line = f"DTSTART;VALUE=DATE:{data_inicio_obj.strftime('%Y%m%d')}"
        # Pela RFC 5545, DTEND em evento de dia inteiro é exclusivo (dia seguinte ao término).
        dtend_exclusivo = data_termino_obj + timedelta(days=1)
        dtend_line = f"DTEND;VALUE=DATE:{dtend_exclusivo.strftime('%Y%m%d')}"
    else:
        hora_inicio_obj = _parse_hhmm_time(dados_evento.get("hora_inicio"), "hora_inicio")
        hora_fim_obj = _parse_hhmm_time(dados_evento.get("hora_fim"), "hora_fim")
        dtstart_line = f"DTSTART:{data_inicio_obj.strftime('%Y%m%d')}T{hora_inicio_obj.strftime('%H%M')}00"
        dtend_line = f"DTEND:{data_termino_obj.strftime('%Y%m%d')}T{hora_fim_obj.strftime('%H%M')}00"

    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SGPJ//Sistema Gerenciador de Processos Judiciais//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        dtstart_line,
        dtend_line,
        f"SUMMARY:{_escapar_texto_ics(titulo)}",
    ]

    if descricao:
        linhas.append(f"DESCRIPTION:{_escapar_texto_ics(descricao)}")
    if local:
        linhas.append(f"LOCATION:{_escapar_texto_ics(local)}")

    linhas.extend([
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ])

    if lembrete and str(lembrete).strip() not in {"", "0"}:
        linhas.extend([
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Lembrete: {_escapar_texto_ics(titulo)}",
            f"TRIGGER:{str(lembrete).strip()}",
            "END:VALARM",
        ])

    linhas.extend([
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    conteudo_ics = "\r\n".join(linhas)
    filename = _slugificar_nome_arquivo(titulo, data_inicio_str)

    return {
        "filename": filename,
        "title": titulo,
        "content": conteudo_ics,
        "mime_type": "text/calendar;charset=utf-8",
    }


@tool(
    "gerarEventoIcs",
    args_schema=GerarEventoIcsInput,
    response_format="content_and_artifact",
)
def gerarEventoIcs(
    titulo: str,
    data_inicio: str,
    dia_inteiro: bool,
    hora_inicio: str | None = None,
    hora_fim: str | None = None,
    data_termino: str | None = None,
    descricao: str | None = None,
    local: str | None = None,
    lembrete: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Valida e registra os dados de um compromisso para geração de arquivo de calendário (.ics).
    Sempre exige titulo, data_inicio e dia_inteiro; para eventos não dia inteiro, exige hora_inicio e hora_fim.
    """
    titulo_limpo = (titulo or "").strip()
    if not titulo_limpo:
        return "Erro de validação: o campo 'titulo' é obrigatório e não pode estar vazio.", None

    try:
        inicio_date = _parse_iso_date(data_inicio, "data_inicio")
        termino_date = (
            _parse_iso_date(data_termino, "data_termino")
            if data_termino and data_termino.strip()
            else inicio_date
        )
    except ValueError as err:
        return f"Erro de validação: {err}", None

    if termino_date < inicio_date:
        return "Erro de validação: 'data_termino' não pode ser anterior a 'data_inicio'.", None

    hora_inicio_fmt: str | None = None
    hora_fim_fmt: str | None = None

    if not dia_inteiro:
        try:
            inicio_time = _parse_hhmm_time(hora_inicio, "hora_inicio")
            fim_time = _parse_hhmm_time(hora_fim, "hora_fim")
        except ValueError as err:
            return f"Erro de validação: {err}", None

        if datetime.combine(termino_date, fim_time) <= datetime.combine(inicio_date, inicio_time):
            return (
                "Erro de validação: a data e horário de término devem ser posteriores "
                "à data e horário de início.",
                None,
            )

        hora_inicio_fmt = inicio_time.strftime("%H:%M")
        hora_fim_fmt = fim_time.strftime("%H:%M")

    lembrete_fmt: str | None = None
    if lembrete and lembrete.strip() and lembrete.strip() != "0":
        candidato = lembrete.strip().upper()
        if not _LEMBRETE_PATTERN.fullmatch(candidato):
            return (
                "Erro de validação: 'lembrete' deve seguir o formato ISO 8601 negativo "
                "(ex: -PT15M, -PT30M, -PT1H, -PT2H, -P1D, -P2D, -P1W).",
                None,
            )
        lembrete_fmt = candidato

    descricao_limpa = descricao.strip() if isinstance(descricao, str) and descricao.strip() else None
    local_limpo = local.strip() if isinstance(local, str) and local.strip() else None

    artifact: dict[str, Any] = {
        "titulo": titulo_limpo,
        "data_inicio": inicio_date.isoformat(),
        "data_termino": termino_date.isoformat(),
        "dia_inteiro": dia_inteiro,
        "hora_inicio": hora_inicio_fmt,
        "hora_fim": hora_fim_fmt,
        "descricao": descricao_limpa,
        "local": local_limpo,
        "lembrete": lembrete_fmt,
    }

    horario_resumo = "Dia inteiro" if dia_inteiro else f"{hora_inicio_fmt} às {hora_fim_fmt}"
    resumo = (
        f"Arquivo .ics preparado com sucesso para o evento '{titulo_limpo}' "
        f"(início: {inicio_date.isoformat()}, término: {termino_date.isoformat()}, "
        f"horário: {horario_resumo}"
        f"{f', local: {local_limpo}' if local_limpo else ''}"
        f"{f', lembrete: {lembrete_fmt}' if lembrete_fmt else ''}). "
        "O arquivo será disponibilizado para download pela aplicação."
    )
    return resumo, artifact


__all__ = ["testeTool", "GerarEventoIcsInput", "gerarEventoIcs", "compilar_anexo_ics"]