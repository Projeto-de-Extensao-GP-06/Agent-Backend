from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.service.agent_service import executar_pipeline_agente

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | UUID | None = None

    @field_validator("message")
    @classmethod
    def validar_mensagem(cls, valor: str) -> str:
        valor_normalizado = valor.strip()
        if not valor_normalizado:
            raise ValueError("A mensagem nao pode estar vazia")
        return valor_normalizado


class ChatResponse(BaseModel):
    response: str
    session_id: str | UUID


@router.post("/chat", response_model=ChatResponse, status_code=200)
async def enviar_mensagem(requisicao: ChatRequest) -> ChatResponse:
    id_sessao: str | UUID = requisicao.session_id or str(uuid4())

    try:
        resposta = await executar_pipeline_agente(
            mensagem=requisicao.message,
            id_sessao=str(id_sessao),
        )
    except Exception as excecao:
        raise HTTPException(
            status_code=502,
            detail="Falha na comunicação com o assistente",
        ) from excecao

    return ChatResponse(response=resposta, session_id=id_sessao)