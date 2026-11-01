class RateLimitExceededException(Exception):
    """Exceção lançada quando o rate limit é excedido."""
    pass


class TokenBlacklistedException(Exception):
    """Exceção lançada quando um token está na blacklist."""
    pass


class AuthenticationException(Exception):
    """Exceção lançada quando a autenticação falha."""
    pass
