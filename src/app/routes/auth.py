from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.app.security.jwt_manager import jwt_manager
from src.app.security.auth import get_current_user

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
async def get_me(current_user: str = Depends(get_current_user)) -> dict:
    """
    Retorna informações do usuário autenticado.

    Similar ao endpoint /auth/me do Backend Java.
    """
    return {
        "email": current_user,
        "authenticated": True
    }


__all__ = ["router"]
