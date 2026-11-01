import threading
from datetime import datetime
from typing import Optional

from src.app.security.jwt_manager import jwt_manager


class TokenBlacklistService:
    """
    Serviço para gerenciar blacklist de tokens JWT.

    Permite revogar tokens imediatamente (logout, comprometimento)
    armazenando-os em memória com limpeza automática de entradas expiradas.
    """

    def __init__(self):
        # Thread-safe dictionary para armazenar tokens revogados
        # Key: jti (JWT ID), Value: datetime de expiração
        self._blacklisted_tokens = {}
        self._lock = threading.Lock()

    def blacklist_token(self, token: str) -> None:
        """
        Adiciona um token à blacklist.

        Args:
            token: Token JWT a ser revogado
        """
        try:
            jti = jwt_manager.get_jti_from_token(token)
            if not jti:
                return

            payload = jwt_manager.verify_token(token)
            if not payload:
                return

            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                expiration = datetime.fromtimestamp(exp_timestamp)
            else:
                # Se não conseguir extrair expiração, usa 1 hora por padrão
                expiration = datetime.utcnow()

            with self._lock:
                self._blacklisted_tokens[jti] = expiration
        except Exception:
            # Se o token for inválido, não precisa fazer nada
            pass

    def is_token_blacklisted(self, token: str) -> bool:
        """
        Verifica se um token está na blacklist.

        Args:
            token: Token JWT a ser verificado

        Returns:
            True se o token está revogado
        """
        try:
            jti = jwt_manager.get_jti_from_token(token)
            if not jti:
                return False

            with self._lock:
                expiration = self._blacklisted_tokens.get(jti)

                if expiration is None:
                    return False

                # Limpa entradas expiradas e retorna False se expirado
                if expiration < datetime.utcnow():
                    del self._blacklisted_tokens[jti]
                    return False

                return True
        except Exception:
            return False

    def cleanup_expired_tokens(self) -> None:
        """
        Remove tokens expirados da blacklist.
        Deve ser chamado periodicamente (ex: scheduler).
        """
        with self._lock:
            now = datetime.utcnow()
            expired_jtis = [
                jti for jti, exp in self._blacklisted_tokens.items()
                if exp < now
            ]
            for jti in expired_jtis:
                del self._blacklisted_tokens[jti]

    def clear_all(self) -> None:
        """
        Limpa todos os tokens da blacklist.
        Útil para testes ou emergências.
        """
        with self._lock:
            self._blacklisted_tokens.clear()

    def get_blacklist_size(self) -> int:
        """
        Retorna o tamanho atual da blacklist.

        Returns:
            Número de tokens revogados
        """
        with self._lock:
            return len(self._blacklisted_tokens)


token_blacklist = TokenBlacklistService()
