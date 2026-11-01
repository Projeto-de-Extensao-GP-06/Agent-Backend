from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.app.security.jwt_manager import jwt_manager
from src.app.security.token_blacklist import token_blacklist
from src.app.security.exceptions import TokenBlacklistedException, AuthenticationException


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Dependência do FastAPI para extrair e validar o usuário autenticado.

    Verifica:
    1. Token presente no header Authorization: Bearer
    2. Token válido (assinatura e expiração)
    3. Token não está na blacklist

    Args:
        credentials: Credenciais do header Authorization

    Returns:
        Email do usuário autenticado

    Raises:
        HTTPException: Se a autenticação falhar
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Versão opcional da autenticação - não exige token.

    Se o token for fornecido e válido, retorna o email.
    Se não for fornecido ou for inválido, retorna None.

    Args:
        credentials: Credenciais do header Authorization

    Returns:
        Email do usuário ou None
    """
    if credentials is None:
        return None

    token = credentials.credentials

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
    async def check_scope(email: str = Depends(get_current_user)) -> str:
        # Recarrega o payload para verificar o scope
        # Em produção, poderíamos passar o payload pelo contexto
        credentials = await security()
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token não fornecido",
            )

        token = credentials.credentials
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
