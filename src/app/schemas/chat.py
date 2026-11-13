from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | UUID | None = None
    dados_processo: dict[str, Any] | None = None
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


class ResumoResponse(BaseModel):
    response: str
    session_id: str | UUID
    attachments: list[IcsAttachment] = Field(default_factory=list)


class ChatResponse(BaseModel):
    resumo_response: ResumoResponse
    raw_response: dict[str, Any] | None = None


class ChatDeleteResponse(BaseModel):
    message: str
    session_id: str | UUID


__all__ = [
    "ChatRequest",
    "IcsAttachment",
    "ResumoResponse",
    "ChatResponse",
    "ChatDeleteResponse",
]
