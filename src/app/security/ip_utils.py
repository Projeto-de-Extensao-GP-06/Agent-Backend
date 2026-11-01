from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Extrai o IP do cliente da requisição.

    Considera proxies e load balancers (X-Forwarded-For).

    Args:
        request: Objeto de requisição FastAPI

    Returns:
        IP do cliente
    """
    # Tenta pegar do header X-Forwarded-For (proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Pega o primeiro IP da lista
        return forwarded.split(",")[0].strip()

    # Tenta pegar do header X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback para o IP direto
    if request.client:
        return request.client.host

    return "unknown"


def create_rate_limit_identifier(request: Request, email: str = None) -> str:
    """
    Cria um identificador único para rate limiting.

    Combina IP e email (se fornecido) para prevenir abuso.

    Similar ao IpAddressUtil.createRateLimitIdentifier do Backend Java.

    Args:
        request: Objeto de requisição FastAPI
        email: Email do usuário (opcional)

    Returns:
        Identificador para rate limiting
    """
    ip = get_client_ip(request)

    if email:
        return f"{ip}:{email}"

    return ip
