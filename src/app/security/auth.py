from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.app.security.jwt_manager import jwt_manager
from src.app.security.token_blacklist import token_blacklist
from src.app.security.middleware import get_token_from_request


security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Dependência do FastAPI para extrair e validar o usuário autenticado.

    Verifica:
    1. Token presente no cookie HttpOnly "authToken" OU header Authorization: Bearer
    2. Token válido (assinatura e expiração)
    3. Token não está na blacklist

    Args:
        request: Objeto de requisição FastAPI
        credentials: Credenciais do header Authorization (fallback)

    Returns:
        Email do usuário autenticado

    Raises:
        HTTPException: Se a autenticação falhar
    """
    # Tenta extrair do cookie ou header
    token = get_token_from_request(request)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verifica se o token está na blacklist
    if token_blacklist.is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token foi revogado. Por favor, faça login novamente.",
        )

    # Verifica e decodifica o token
    payload = jwt_manager.verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não contém usuário válido",
        )

    return email


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Versão opcional da autenticação - não exige token.

    Se o token for fornecido e válido, retorna o email.
    Se não for fornecido ou for inválido, retorna None.

    Args:
        request: Objeto de requisição FastAPI
        credentials: Credenciais do header Authorization (fallback)

    Returns:
        Email do usuário ou None
    """
    token = get_token_from_request(request)

    if not token:
        return None

    if token_blacklist.is_token_blacklisted(token):
        return None

    payload = jwt_manager.verify_token(token)
    if payload is None:
        return None

    return payload.get("sub")


class RequireScope:
    """
    Callable para verificar escopo do token com FastAPI Depends.

    Equivalente ao @PreAuthorize do Spring Security.
    """

    def __init__(self, required_scope: str):
        self.required_scope = required_scope

    async def __call__(self, request: Request) -> str:
        """
        Verifica o escopo do token.

        Args:
            request: Objeto de requisição FastAPI

        Returns:
            Email do usuário autenticado

        Raises:
            HTTPException: Se o escopo não corresponder
        """
        token = get_token_from_request(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token não fornecido",
            )

        payload = jwt_manager.verify_token(token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
            )

        scope = payload.get("scope")
        if scope != self.required_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Escopo '{self.required_scope}' necessário para esta operação",
            )

        email = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token não contém usuário válido",
            )

        return email


# Instâncias callable para uso com Depends()
require_general_use = RequireScope("GENERAL_USE")
require_set_password = RequireScope("SET_PASSWORD")

