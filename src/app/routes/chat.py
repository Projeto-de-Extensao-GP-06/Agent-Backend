import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends, Request

from src.app.schemas.chat import ChatDeleteResponse, ChatRequest, ChatResponse
from src.app.services.agent_service import excluirSessao, executarPipelineAgente
from src.app.security.auth import get_current_user, require_general_use
from src.app.security.rate_limiter import rate_limiter
from src.app.security.ip_utils import create_rate_limit_identifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, status_code=200)
async def enviarMensagem(
    requisicao: ChatRequest,
    request: Request,
    current_user: str = Depends(require_general_use())
) -> ChatResponse:
    """
    Endpoint para enviar mensagem ao assistente.

    Requer autenticação JWT com escopo GENERAL_USE.
    Token pode ser fornecido via cookie HttpOnly "authToken" ou header Authorization: Bearer.
    """
    # Rate limiting por usuário autenticado
    identifier = create_rate_limit_identifier(request, current_user)
    rate_limiter.check_rate_limit(identifier)

    idSessao: str | UUID = requisicao.session_id or str(uuid4())

    try:
        respostaCompleta = await executarPipelineAgente(
            mensagem=requisicao.message,
            idSessao=str(idSessao),
            dadosProcesso=requisicao.dados_processo,
        )
    except ValueError as excecao:
        raise HTTPException(status_code=400, detail=str(excecao)) from excecao
    except Exception as excecao:
        logger.exception("Erro ao processar mensagem no assistente")
        raise HTTPException(
            status_code=502,
            detail=f"Falha na comunicacao com o assistente: {excecao}",
        ) from excecao

    return ChatResponse(
        resumo_response={
            "response": respostaCompleta["resposta"],
            "session_id": idSessao,
        },
        raw_response=respostaCompleta.get("raw_response"),
    )


@router.delete("/chat/{session_id}", response_model=ChatDeleteResponse, status_code=200)
async def excluirChat(
    session_id: str,
    request: Request,
    current_user: str = Depends(require_general_use())
) -> ChatDeleteResponse:
    """
    Endpoint para excluir uma sessão de chat.

    Requer autenticação JWT com escopo GENERAL_USE.
    Token pode ser fornecido via cookie HttpOnly "authToken" ou header Authorization: Bearer.
    """
    # Rate limiting por usuário autenticado
    identifier = create_rate_limit_identifier(request, current_user)
    rate_limiter.check_rate_limit(identifier)

    if not excluirSessao(session_id):
        raise HTTPException(status_code=404, detail="Thread nao encontrada")

    return ChatDeleteResponse(
        message="Chat excluído com sucesso",
        session_id=session_id,
    )


__all__ = ["router", "enviarMensagem", "excluirChat"]
