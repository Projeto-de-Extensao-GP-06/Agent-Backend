from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class AuthCookieMiddleware(BaseHTTPMiddleware):
    """
    Middleware para extrair token JWT de cookie HttpOnly ou header Authorization.

    Prioridade:
    1. Cookie HttpOnly "authToken" (usado pelo browser)
    2. Header Authorization: Bearer (fallback para Swagger, Postman, server-to-server)

    O token extraído é armazenado no estado da requisição para uso posterior.
    """

    async def dispatch(self, request: Request, call_next):
        # Tenta extrair do cookie primeiro
        token = request.cookies.get("authToken")
        print(f"[MIDDLEWARE] Cookie authToken: {token[:50] if token else 'None'}...")

        # Se não encontrou no cookie, tenta do header Authorization
        if not token:
            auth_header = request.headers.get("Authorization")
            print(f"[MIDDLEWARE] Authorization header: {auth_header}")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer "

        # Armazena o token no estado da requisição
        if token:
            request.state.auth_token = token
            print(f"[MIDDLEWARE] Token stored in state: {token[:50]}...")

        response = await call_next(request)
        return response


def get_token_from_request(request: Request) -> Optional[str]:
    """
    Extrai o token JWT da requisição (cookie ou header).

    Args:
        request: Objeto de requisição FastAPI

    Returns:
        Token JWT ou None
    """
    # Tenta do estado (setado pelo middleware)
    token = getattr(request.state, "auth_token", None)
    if token:
        return token

    # Fallback direto (caso middleware não seja usado)
    token = request.cookies.get("authToken")
    if token:
        return token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None
