import threading
from datetime import datetime, timedelta
from typing import Optional
from collections import deque

from src.app.security.exceptions import RateLimitExceededException


class RateLimiter:
    """
    Rate limiter usando sliding window para prevenir abuso de endpoints públicos.

    Segue as mesmas configurações do Backend Java:
    - Login: 10/min, 30/hora
    - OTP: 5/min, 20/hora
    - Forms: 10/min, 60/hora
    - Geral: 60/min, 1000/hora
    """

    def __init__(self):
        # Thread-safe dictionary para histórico de requisições
        # Key: identifier:time_unit, Value: deque de timestamps
        self._request_history = {}
        self._lock = threading.Lock()

        # Configurações de rate limit
        self.MAX_REQUESTS_PER_MINUTE = 60
        self.MAX_REQUESTS_PER_HOUR = 1000

        self.MAX_LOGIN_REQUESTS_PER_MINUTE = 10
        self.MAX_LOGIN_REQUESTS_PER_HOUR = 30

        self.MAX_OTP_REQUESTS_PER_MINUTE = 5
        self.MAX_OTP_REQUESTS_PER_HOUR = 20

        self.MAX_FORM_REQUESTS_PER_MINUTE = 10
        self.MAX_FORM_REQUESTS_PER_HOUR = 60

    def check_rate_limit(self, identifier: str) -> None:
        """
        Verifica rate limit para endpoints públicos gerais.

        Args:
            identifier: Identificador único (email, IP, etc.)

        Raises:
            RateLimitExceededException: Se o limite for excedido
        """
        self._check_rate_limit(identifier, self.MAX_REQUESTS_PER_HOUR, timedelta(hours=1))
        self._check_rate_limit(identifier, self.MAX_REQUESTS_PER_MINUTE, timedelta(minutes=1))

    def check_login_rate_limit(self, identifier: str) -> None:
        """
        Verifica rate limit para endpoints de login (mais restrito).

        Args:
            identifier: Identificador único (email, IP, etc.)

        Raises:
            RateLimitExceededException: Se o limite for excedido
        """
        self._check_rate_limit(identifier, self.MAX_LOGIN_REQUESTS_PER_HOUR, timedelta(hours=1))
        self._check_rate_limit(identifier, self.MAX_LOGIN_REQUESTS_PER_MINUTE, timedelta(minutes=1))

    def check_otp_rate_limit(self, identifier: str) -> None:
        """
        Verifica rate limit para endpoints de OTP (mais restrito).

        Args:
            identifier: Identificador único (email, IP, etc.)

        Raises:
            RateLimitExceededException: Se o limite for excedido
        """
        self._check_rate_limit(identifier, self.MAX_OTP_REQUESTS_PER_HOUR, timedelta(hours=1))
        self._check_rate_limit(identifier, self.MAX_OTP_REQUESTS_PER_MINUTE, timedelta(minutes=1))

    def check_form_rate_limit(self, identifier: str) -> None:
        """
        Verifica rate limit para endpoints de formulário.

        Args:
            identifier: Identificador único (email, IP, etc.)

        Raises:
            RateLimitExceededException: Se o limite for excedido
        """
        self._check_rate_limit(identifier, self.MAX_FORM_REQUESTS_PER_HOUR, timedelta(hours=1))
        self._check_rate_limit(identifier, self.MAX_FORM_REQUESTS_PER_MINUTE, timedelta(minutes=1))

    def _check_rate_limit(self, identifier: str, max_requests: int, time_window: timedelta) -> None:
        """
        Lógica principal de rate limiting usando sliding window.

        Args:
            identifier: Identificador único
            max_requests: Máximo de requisições permitidas
            time_window: Janela de tempo

        Raises:
            RateLimitExceededException: Se o limite for excedido
        """
        if not identifier:
            raise ValueError("Identifier cannot be empty")

        key = f"{identifier}:{time_window.total_seconds()}"

        with self._lock:
            if key not in self._request_history:
                self._request_history[key] = deque()

            history = self._request_history[key]
            now = datetime.utcnow()
            window_start = now - time_window

            # Remove requisições fora da janela de tempo
            while history and history[0] < window_start:
                history.popleft()

            # Verifica se excedeu o limite
            if len(history) >= max_requests:
                time_unit_str = "minute" if time_window.total_seconds() == 60 else "hour"
                raise RateLimitExceededException(
                    f"Rate limit exceeded: maximum {max_requests} requests per {time_unit_str} allowed"
                )

            # Registra esta requisição
            history.append(now)

    def clear_all(self) -> None:
        """
        Limpa todo o histórico de rate limit.
        Útil para testes.
        """
        with self._lock:
            self._request_history.clear()

    def clear_for_identifier(self, identifier: str) -> None:
        """
        Limpa o histórico de rate limit para um identificador específico.

        Args:
            identifier: Identificador a ser limpo
        """
        with self._lock:
            keys_to_remove = [key for key in self._request_history.keys() if key.startswith(identifier + ":")]
            for key in keys_to_remove:
                del self._request_history[key]


rate_limiter = RateLimiter()
