from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | UUID | None = None
    dados_processo: dict[str, Any] | None = None
    dados_dashboard: dict[str, Any] | None = None
    timezone: str | None = None

    @field_validator("message")
    @classmethod
    def validarMensagem(cls, valor: str) -> str:
        valorNormalizado = valor.strip()
        if not valorNormalizado:
            raise ValueError("A mensagem nao pode estar vazia")
        return valorNormalizado


class IcsAttachment(BaseModel):
    filename: str
    title: str
    content: str
    mime_type: str = "text/calendar;charset=utf-8"


class ChartSeries(BaseModel):
    data_key: str
    name: str
    color: str | None = None


class ChartAttachment(BaseModel):
    title: str
    subtitle: str | None = None
    chart_type: Literal["bar", "horizontal_bar", "line", "pie"] = "bar"
    x_key: str = "label"
    data: list[dict[str, Any]] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    palette: str | None = None


class ResumoResponse(BaseModel):
    response: str
    session_id: str | UUID
    attachments: list[IcsAttachment] = Field(default_factory=list)
    charts: list[ChartAttachment] = Field(default_factory=list)


class ChatResponse(BaseModel):
    resumo_response: ResumoResponse
    raw_response: dict[str, Any] | None = None


class ChatDeleteResponse(BaseModel):
    message: str
    session_id: str | UUID


__all__ = [
    "ChatRequest",
    "IcsAttachment",
    "ChartSeries",
    "ChartAttachment",
    "ResumoResponse",
    "ChatResponse",
    "ChatDeleteResponse",
]
