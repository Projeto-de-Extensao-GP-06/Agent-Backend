from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.app.security.jwt_manager import jwt_manager
from src.app.security.auth import get_current_user, require_general_use
from src.app.security.token_blacklist import token_blacklist
from src.app.security.middleware import get_token_from_request
from src.app.security.ip_utils import create_rate_limit_identifier
from src.app.security.rate_limiter import rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenValidationResponse(BaseModel):
    valid: bool
    email: str | None = None
    scope: str | None = None


@router.get("/validate", response_model=TokenValidationResponse)
async def validate_token(current_user: str = Depends(get_current_user)) -> TokenValidationResponse:
    """
    Valida um token JWT e retorna informações do usuário.

    Este endpoint verifica se o token fornecido é válido e
    retorna o email e escopo do usuário autenticado.

    Útil para o frontend verificar se o token ainda é válido
    antes de fazer requisições ao agent.
    """
    # Se chegou aqui, o token é válido (get_current_user já validou)
    # Em um cenário real, poderíamos buscar mais informações do usuário
    # em um banco de dados ou fazer uma chamada ao Backend Java

    return TokenValidationResponse(
        valid=True,
        email=current_user,
        scope="GENERAL_USE"  # Escopo padrão, poderia ser extraído do token
    )


@router.get("/me")
async def get_me(current_user: str = Depends(require_general_use())) -> dict:
    """
    Retorna informações do usuário autenticado.

    Similar ao endpoint /auth/me do Backend Java.
    Requer escopo GENERAL_USE.
    """
    return {
        "email": current_user,
        "authenticated": True
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: str = Depends(get_current_user)
) -> JSONResponse:
    """
    Faz logout do usuário.

    Revoga o access token atual (adiciona à blacklist) e
    remove os cookies de autenticação.

    Similar ao endpoint /auth/logout do Backend Java.
    """
    token = get_token_from_request(request)

    if token:
        token_blacklist.blacklist_token(token)

    # Remove cookies
    response.delete_cookie(
        key="authToken",
        path="/",
        httponly=True,
        secure=True,
        samesite="strict"
    )

    response.delete_cookie(
        key="refreshToken",
        path="/auth",
        httponly=True,
        secure=True,
        samesite="strict"
    )

    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=None
    )


@router.post("/refresh-token")
async def refresh_token(
    request: Request,
    response: Response
) -> JSONResponse:
    """
    Renova o access token usando o refresh token.

    Este endpoint deve ser chamado pelo Backend Java (via proxy)
    ou implementar a lógica completa de refresh token aqui.

    NOTA: Esta é uma implementação simplificada. Em produção,
    o refresh token deve ser validado no Backend Java que tem
    o banco de dados de usuários.

    Similar ao endpoint /auth/refresh-token do Backend Java.
    """
    # Extrai refresh token do cookie
    refresh_token = request.cookies.get("refreshToken")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token não fornecido"
        )

    # Extrai access token atual para blacklist
    access_token = get_token_from_request(request)
    if access_token:
        token_blacklist.blacklist_token(access_token)

    # NOTA: Em produção, aqui você deve:
    # 1. Validar o refresh token no Backend Java
    # 2. Obter novo access token do Backend Java
    # 3. Retornar o novo access token

    # Por enquanto, retorna erro indicando que deve usar o Backend Java
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Refresh token deve ser validado no Backend Java. Use o endpoint /auth/refresh-token do Backend Java."
    )


__all__ = ["router"]
