from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.app.security.jwt_manager import jwt_manager
from src.app.security.token_blacklist import token_blacklist
from src.app.security.middleware import get_token_from_request
from src.app.security.exceptions import TokenBlacklistedException, AuthenticationException


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


async def require_scope(required_scope: str):
    """
    Factory para criar dependência que verifica o escopo do token.

    Args:
        required_scope: Escopo necessário (ex: "GENERAL_USE", "SET_PASSWORD")

    Returns:
        Função de dependência para FastAPI
    """
    async def check_scope(
        request: Request,
        email: str = Depends(get_current_user)
    ) -> str:
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
        if scope != required_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Escopo '{required_scope}' necessário para esta operação",
            )

        return email

    return check_scope


def require_general_use():
    """
    Dependência que exige escopo GENERAL_USE no token.

    Equivalente ao @PreAuthorize("hasAuthority('SCOPE_GENERAL_USE')") do Spring Security.
    """
    return require_scope("GENERAL_USE")


def require_set_password():
    """
    Dependência que exige escopo SET_PASSWORD no token.

    Equivalente ao @PreAuthorize("hasAuthority('SCOPE_SET_PASSWORD')") do Spring Security.
    """
    return require_scope("SET_PASSWORD")

