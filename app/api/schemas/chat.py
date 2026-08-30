from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | UUID | None = None
    dados_processo: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def validarMensagem(cls, valor: str) -> str:
        valorNormalizado = valor.strip()
        if not valorNormalizado:
            raise ValueError("A mensagem nao pode estar vazia")
        return valorNormalizado


class ResumoResponse(BaseModel):
    response: str
    session_id: str | UUID


class ChatResponse(BaseModel):
    resumo_response: ResumoResponse
    raw_response: dict[str, Any] | None = None


class ChatDeleteResponse(BaseModel):
    message: str
    session_id: str | UUID
