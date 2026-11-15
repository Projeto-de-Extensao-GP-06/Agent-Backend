import json
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from langchain.tools import tool
from langgraph.prebuilt import InjectedState
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


def _estruturar_snapshot_dashboard(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Organiza os dados brutos da Dashboard (gerais e filtrados) em um dicionário claro para o LLM."""
    periodo_raw = snapshot.get("periodo") if isinstance(snapshot.get("periodo"), dict) else {}
    general = snapshot.get("dadosGerais") if isinstance(snapshot.get("dadosGerais"), dict) else snapshot
    filtered = snapshot.get("dadosFiltrados") if isinstance(snapshot.get("dadosFiltrados"), dict) else snapshot

    applied_period = (
        periodo_raw.get("appliedPeriod")
        or snapshot.get("appliedPeriod")
        or "Mês atual"
    )
    date_from = periodo_raw.get("dateFrom") or snapshot.get("dateFrom") or ""
    date_to = periodo_raw.get("dateTo") or snapshot.get("dateTo") or ""

    fases_raw = general.get("processosPorFase") if isinstance(general.get("processosPorFase"), list) else []
    processos_por_fase = [
        {
            "fase": item.get("nomeFase") or "Não informada",
            "quantidade_processos": int(item.get("qtdProcessos") or 0),
        }
        for item in fases_raw
        if isinstance(item, dict)
    ]

    duracao_raw = (
        general.get("tempoDuracaoProcessos")
        if isinstance(general.get("tempoDuracaoProcessos"), dict)
        else {}
    )
    tempo_duracao = {
        "0_a_6_meses": int(duracao_raw.get("ate6Meses") or 0),
        "6_a_12_meses": int(duracao_raw.get("de6a12Meses") or 0),
        "1_a_2_anos": int(duracao_raw.get("de1a2Anos") or 0),
        "2_a_5_anos": int(duracao_raw.get("de2a5Anos") or 0),
        "mais_de_5_anos": int(duracao_raw.get("mais5Anos") or 0),
    }

    audiencias_raw = general.get("audiencias") if isinstance(general.get("audiencias"), list) else []
    agenda_risco = [
        {
            "data_audiencia": item.get("dataAudiencia"),
            "fase": item.get("nomeFaseProcesso") or "—",
            "responsavel": item.get("nomeUsuarioResponsavel") or item.get("emailUsuarioResponsavel") or "—",
            "cliente": item.get("nomeCliente") or "—",
            "prioridade": item.get("nomePrioridade") or "Média",
        }
        for item in audiencias_raw
        if isinstance(item, dict)
    ]

    encerrados_raw = (
        filtered.get("processosEncerrados")
        if isinstance(filtered.get("processosEncerrados"), dict)
        else {}
    )
    encerrados_categorias = {
        "Acordo": int(encerrados_raw.get("encerradosPorAcordo") or 0),
        "Sem resolução": int(encerrados_raw.get("encerradosPorSemResolucao") or 0),
        "Penhora Total": int(encerrados_raw.get("encerradosPorPenhoraTotal") or 0),
        "Pagamento voluntário": int(encerrados_raw.get("encerradosPorPagamentoVoluntario") or 0),
        "Outros": int(encerrados_raw.get("encerradosPorOutros") or 0),
    }

    suspensos_raw = (
        filtered.get("processosSuspensos")
        if isinstance(filtered.get("processosSuspensos"), dict)
        else {}
    )
    suspensos_categorias = {
        "Acordo Parcelado": int(suspensos_raw.get("suspensosPorAcordoParcelado") or 0),
        "Tratativas": int(suspensos_raw.get("suspensosPorTratativas") or 0),
        "Ausência de Bens": int(suspensos_raw.get("suspensosPorAusenciaDeBens") or 0),
        "Determinação Judicial": int(suspensos_raw.get("suspensosPorDeterminacaoJudicial") or 0),
        "Outros": int(suspensos_raw.get("suspensosPorOutros") or 0),
    }

    formas_raw = (
        filtered.get("formasDeEntrada")
        if isinstance(filtered.get("formasDeEntrada"), dict)
        else (
            general.get("formasDeEntrada")
            if isinstance(general.get("formasDeEntrada"), dict)
            else {}
        )
    )
    formas_entrada = {
        "Instagram": int(formas_raw.get("instagram") or 0),
        "Site": int(formas_raw.get("site") or 0),
        "Indicação": int(formas_raw.get("indicacao") or 0),
    }

    evolucao_raw = (
        filtered.get("evolucaoCarteira")
        if isinstance(filtered.get("evolucaoCarteira"), dict)
        else {}
    )
    evolucao_carteira = {
        "ativos": int(evolucao_raw.get("ativos") or 0),
        "encerrados": int(evolucao_raw.get("encerrados") or 0),
        "suspensos": int(evolucao_raw.get("suspensos") or 0),
        "novos": int(evolucao_raw.get("novos") or 0),
    }

    return {
        "periodo_filtrado": {
            "rotulo": applied_period,
            "data_inicio": date_from,
            "data_fim": date_to,
        },
        "kpis_gerais_sistema": {
            "processos_ativos": int(general.get("processoAtivos") or 0),
            "solicitacoes_pendentes": int(general.get("solicitacoesPendentes") or 0),
            "clientes_cadastrados": int(general.get("clientesExistentes") or 0),
            "processos_com_audiencia": int(general.get("processosComAudiencia") or 0),
        },
        "processos_por_fase": processos_por_fase,
        "tempo_duracao_processos_ativos": tempo_duracao,
        "agenda_risco_audiencias": agenda_risco,
        "indicadores_do_periodo": {
            "processos_encerrados_por_categoria": {
                "categorias": encerrados_categorias,
                "total": sum(encerrados_categorias.values()),
            },
            "processos_suspensos_por_categoria": {
                "categorias": suspensos_categorias,
                "total": sum(suspensos_categorias.values()),
            },
            "formas_de_entrada_clientes": {
                "canais": formas_entrada,
                "total": sum(formas_entrada.values()),
            },
            "evolucao_da_carteira": evolucao_carteira,
        },
    }


class ConsultarDadosDashboardInput(BaseModel):
    """Parâmetros de entrada para consulta dos dados de performance da Dashboard do SGPJ."""

    indicadores: list[str] | None = Field(
        default=None,
        description=(
            "Lista opcional de seções a consultar: 'kpis_gerais', 'processos_por_fase', "
            "'tempo_duracao', 'agenda_risco', 'processos_encerrados', 'processos_suspensos', "
            "'formas_de_entrada', 'evolucao_carteira', 'comparacao_periodos' ou 'todos'. "
            "Se omitido, retorna todos os indicadores disponíveis."
        ),
    )
    state: Annotated[dict[str, Any], InjectedState] = Field(default_factory=dict)


@tool("consultarDadosDashboard", args_schema=ConsultarDadosDashboardInput)
def consultarDadosDashboard(
    indicadores: list[str] | None = None,
    state: Annotated[dict[str, Any], InjectedState] = None,
) -> str:
    """
    Busca os dados de performance do negócio da Dashboard do SGPJ (KPIs gerais, processos por fase,
    tempo de duração, agenda de risco/audiências e indicadores filtrados por período: processos
    encerrados, processos suspensos, formas de entrada de clientes e evolução da carteira).
    Acione esta ferramenta sempre que o usuário perguntar sobre indicadores, métricas, estatísticas
    ou desempenho do escritório/sistema.
    """
    dados_dashboard = (state or {}).get("dados_dashboard") if isinstance(state, dict) else None
    if not dados_dashboard or not isinstance(dados_dashboard, dict):
        return (
            "Não há dados da Dashboard vinculados à conversa no momento. "
            "Oriente o usuário de forma cordial a clicar no botão '+ Vincular dashboard' "
            "(localizado logo acima do campo de mensagem) e selecionar o período desejado "
            "(Hoje, Esta semana, Mês atual, Ano atual ou Personalizado) para que você possa "
            "analisar os indicadores do escritório."
        )

    estruturado = _estruturar_snapshot_dashboard(dados_dashboard)

    historico_raw = dados_dashboard.get("historico_periodos")
    if isinstance(historico_raw, dict) and len(historico_raw) > 1:
        estruturado["historico_periodos_sessao"] = {
            chave: _estruturar_snapshot_dashboard(snap)["indicadores_do_periodo"]
            for chave, snap in historico_raw.items()
            if isinstance(snap, dict)
        }

    return json.dumps(estruturado, ensure_ascii=False, indent=2)


class SerieGraficoInput(BaseModel):
    """Configuração de uma série de dados em um gráfico."""

    data_key: str = Field(
        ...,
        description="Chave numérica presente nos objetos de 'dados' (ex: 'total', 'processos', 'clientes', 'ativos').",
    )
    name: str = Field(
        ...,
        description="Nome legível da série para exibição na legenda e tooltip (ex: 'Processos', 'Clientes', 'Ativos').",
    )
    color: str | None = Field(
        default=None,
        description=(
            "Cor opcional da série (hexadecimal como '#0F2357' ou chave semântica: "
            "'active', 'closed', 'suspended', 'new', 'primary', 'accent')."
        ),
    )


class GerarGraficoDashboardInput(BaseModel):
    """Parâmetros validados para geração de um gráfico visual no chat do frontend."""

    titulo: str = Field(
        ...,
        description="Título principal do gráfico (ex: 'Processos Encerrados por Categoria').",
    )
    subtitulo: str | None = Field(
        default=None,
        description="Subtítulo indicando o escopo ou período (ex: 'Total por categoria - Mês atual').",
    )
    tipo: Literal["bar", "horizontal_bar", "line", "pie"] = Field(
        default="bar",
        description=(
            "Tipo do gráfico a ser renderizado: "
            "'bar' (barras verticais para categorias, durações, canais ou comparações), "
            "'horizontal_bar' (barras horizontais, ideal para distribuição por fases processuais), "
            "'line' (linhas, ideal para evolução temporal ou séries comparativas), "
            "'pie' (rosca/pizza, ideal para proporção percentual entre categorias)."
        ),
    )
    x_key: str = Field(
        default="label",
        description="Chave nos objetos de 'dados' que contém o nome/rótulo de cada item (padrão: 'label').",
    )
    dados: list[dict[str, Any]] = Field(
        ...,
        description=(
            "Lista de pontos de dados do gráfico. Cada item deve conter a chave definida em 'x_key' "
            "(ex: 'label') e ao menos uma chave numérica correspondente às séries "
            "(ex: [{'label': 'Acordo', 'total': 12}, {'label': 'Penhora Total', 'total': 5}])."
        ),
    )
    series: list[SerieGraficoInput] | None = Field(
        default=None,
        description=(
            "Lista de séries numéricas a plotar. Se omitida, será inferida automaticamente "
            "a partir das chaves numéricas presentes em 'dados'."
        ),
    )
    paleta: Literal["brand", "semantic", "closed", "suspended", "duration", "phase", "channels"] = Field(
        default="brand",
        description=(
            "Família de cores oficial do SGPJ: "
            "'brand' (azul marinho #0F2357 e dourado #C9A96E), "
            "'semantic' (ativos=azul, encerrados=vermelho, suspensos=âmbar, novos=verde), "
            "'closed' (família de vermelho para processos encerrados), "
            "'suspended' (família de âmbar para processos suspensos), "
            "'duration' (escala sequencial de azul para tempo de duração), "
            "'phase' (azul marinho com destaque dourado para a fase líder), "
            "'channels' (azul institucional para canais de entrada)."
        ),
    )


def compilar_grafico_dashboard(
    artifact: dict[str, Any],
    session_id: str | None = None,
) -> dict[str, Any]:
    """Desanonimiza rótulos/títulos do gráfico e normaliza o objeto ChartAttachment para o frontend."""
    titulo = str(
        desanonimizar_texto(str(artifact.get("title") or "Indicadores da Dashboard"), session_id=session_id)
    ).strip()
    subtitulo_raw = artifact.get("subtitle")
    subtitulo = (
        str(desanonimizar_texto(str(subtitulo_raw), session_id=session_id)).strip()
        if subtitulo_raw
        else None
    )

    x_key = str(artifact.get("x_key") or "label").strip() or "label"
    dados_raw = artifact.get("data") if isinstance(artifact.get("data"), list) else []
    dados_limpos: list[dict[str, Any]] = []
    for item in dados_raw:
        if not isinstance(item, dict):
            continue
        novo_item: dict[str, Any] = {}
        for k, v in item.items():
            if isinstance(v, str):
                novo_item[k] = desanonimizar_texto(v, session_id=session_id)
            else:
                novo_item[k] = v
        dados_limpos.append(novo_item)

    series_raw = artifact.get("series") if isinstance(artifact.get("series"), list) else []
    series_limpas: list[dict[str, Any]] = []
    for s in series_raw:
        if not isinstance(s, dict):
            continue
        nome_serie = str(desanonimizar_texto(str(s.get("name") or s.get("data_key") or "Valor"), session_id=session_id))
        series_limpas.append(
            {
                "data_key": str(s.get("data_key") or "valor"),
                "name": nome_serie,
                "color": s.get("color"),
            }
        )

    return {
        "title": titulo,
        "subtitle": subtitulo,
        "chart_type": artifact.get("chart_type") or "bar",
        "x_key": x_key,
        "data": dados_limpos,
        "series": series_limpas,
        "palette": artifact.get("palette") or "brand",
    }


@tool(
    "gerarGraficoDashboard",
    args_schema=GerarGraficoDashboardInput,
    response_format="content_and_artifact",
)
def gerarGraficoDashboard(
    titulo: str,
    dados: list[dict[str, Any]],
    subtitulo: str | None = None,
    tipo: Literal["bar", "horizontal_bar", "line", "pie"] = "bar",
    x_key: str = "label",
    series: list[SerieGraficoInput] | None = None,
    paleta: Literal["brand", "semantic", "closed", "suspended", "duration", "phase", "channels"] = "brand",
) -> tuple[str, dict[str, Any] | None]:
    """
    Gera um gráfico interativo no frontend para ilustrar dados e análises da Dashboard do SGPJ.
    Deve ser acionada sempre que um gráfico ajudar a visualizar distribuições, evoluções,
    comparações ou sustentar recomendações sobre o negócio, utilizando exclusivamente os
    valores reais obtidos via consultarDadosDashboard.
    """
    titulo_limpo = (titulo or "").strip()
    if not titulo_limpo:
        return "Erro de validação: 'titulo' do gráfico é obrigatório.", None

    if not dados or not isinstance(dados, list):
        return "Erro de validação: 'dados' deve ser uma lista não vazia de pontos para o gráfico.", None

    x_key_efetivo = (x_key or "label").strip() or "label"

    # Normaliza os itens de dados garantindo que x_key exista
    dados_normalizados: list[dict[str, Any]] = []
    chaves_numericas_detectadas: list[str] = []

    for idx, item in enumerate(dados):
        if not isinstance(item, dict):
            continue
        copia = dict(item)
        if x_key_efetivo not in copia:
            # Tenta encontrar uma chave textual candidata para usar como rótulo
            for k_cand in ("label", "categoria", "fase", "faixa", "origem", "mes", "nome", "periodo"):
                if k_cand in copia:
                    copia[x_key_efetivo] = copia[k_cand]
                    break
            else:
                copia[x_key_efetivo] = f"Item {idx + 1}"

        for k, v in copia.items():
            if k == x_key_efetivo or k == "fill" or k == "color":
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if k not in chaves_numericas_detectadas:
                    chaves_numericas_detectadas.append(k)
            elif isinstance(v, str):
                try:
                    num = float(v.replace(",", "."))
                    copia[k] = int(num) if num.is_integer() else num
                    if k not in chaves_numericas_detectadas:
                        chaves_numericas_detectadas.append(k)
                except ValueError:
                    pass

        dados_normalizados.append(copia)

    if not dados_normalizados or not chaves_numericas_detectadas:
        return (
            "Erro de validação: 'dados' deve conter ao menos um item com valor numérico para plotar.",
            None,
        )

    series_normalizadas: list[dict[str, Any]] = []
    if series:
        for s in series:
            s_dict = s.model_dump() if hasattr(s, "model_dump") else dict(s)
            dk = str(s_dict.get("data_key") or "").strip()
            if dk:
                series_normalizadas.append(
                    {
                        "data_key": dk,
                        "name": str(s_dict.get("name") or dk.capitalize()),
                        "color": s_dict.get("color"),
                    }
                )

    if not series_normalizadas:
        nomes_amigaveis = {
            "total": "Total",
            "processos": "Processos",
            "clientes": "Clientes",
            "valor": "Quantidade",
            "ativos": "Ativos",
            "encerrados": "Encerrados",
            "suspensos": "Suspensos",
            "novos": "Novos",
        }
        for dk in chaves_numericas_detectadas:
            series_normalizadas.append(
                {
                    "data_key": dk,
                    "name": nomes_amigaveis.get(dk.lower(), dk.replace("_", " ").capitalize()),
                    "color": None,
                }
            )

    artifact: dict[str, Any] = {
        "title": titulo_limpo,
        "subtitle": subtitulo.strip() if isinstance(subtitulo, str) and subtitulo.strip() else None,
        "chart_type": tipo,
        "x_key": x_key_efetivo,
        "data": dados_normalizados,
        "series": series_normalizadas,
        "palette": paleta,
    }

    resumo = (
        f"Gráfico '{titulo_limpo}' (tipo: {tipo}, {len(dados_normalizados)} categorias/pontos) "
        "preparado com sucesso e anexado para exibição visual abaixo da resposta no frontend."
    )
    return resumo, artifact


__all__ = [
    "testeTool",
    "GerarEventoIcsInput",
    "gerarEventoIcs",
    "compilar_anexo_ics",
    "ConsultarDadosDashboardInput",
    "consultarDadosDashboard",
    "SerieGraficoInput",
    "GerarGraficoDashboardInput",
    "gerarGraficoDashboard",
    "compilar_grafico_dashboard",
]