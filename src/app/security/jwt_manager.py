import base64
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.app.config.settings import settings


class JWTManager:
    """
    Gerenciador de tokens JWT para autenticação.

    Responsável por gerar, validar e extrair informações de tokens JWT
    usando algoritmo HMAC-SHA256, compatível com o Backend Java.
    """

    def __init__(self):
        # Decode Base64 secret to match Backend Java behavior
        try:
            self.secret_key = base64.b64decode(settings.jwt_secret)
        except Exception:
            # If not valid Base64, use as-is (fallback for development)
            self.secret_key = settings.jwt_secret
        self.algorithm = "HS512"  # Must match Backend Java
        self.access_token_expire_minutes = settings.jwt_validity // 60
        self.refresh_token_expire_days = settings.jwt_refresh_validity // 86400

        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def create_access_token(
        self,
        data: Dict,
        expires_delta: Optional[timedelta] = None,
        scope: str = "GENERAL_USE"
    ) -> str:
        """
        Gera um token JWT de acesso.

        Args:
            data: Dados a serem incluídos no token (ex: email, authorities)
            expires_delta: Tempo de expiração customizado
            scope: Escopo do token (GENERAL_USE, SET_PASSWORD, etc.)

        Returns:
            Token JWT assinado
        """
        to_encode = data.copy()
        to_encode.update({
            "jti": str(uuid.uuid4()),  # JWT ID para revogação
            "scope": scope,
            "iat": datetime.utcnow().timestamp()
        })

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode["exp"] = expire.timestamp()

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def create_refresh_token(self, data: Dict) -> str:
        """
        Gera um token JWT para refresh (maior validade).

        Args:
            data: Dados a serem incluídos no token

        Returns:
            Token JWT de refresh
        """
        to_encode = data.copy()
        to_encode.update({
            "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow().timestamp()
        })

        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode["exp"] = expire.timestamp()

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict]:
        """
        Verifica e decodifica um token JWT.

        Args:
            token: Token JWT a ser verificado

        Returns:
            Payload do token se válido, None caso contrário
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except JWTError:
            return None

    def get_email_from_token(self, token: str) -> Optional[str]:
        """
        Extrai o email (subject) do token.

        Args:
            token: Token JWT

        Returns:
            Email do usuário ou None
        """
        payload = self.verify_token(token)
        if payload:
            return payload.get("sub")
        return None

    def get_jti_from_token(self, token: str) -> Optional[str]:
        """
        Extrai o JWT ID (jti) do token.

        Args:
            token: Token JWT

        Returns:
            JWT ID ou None
        """
        payload = self.verify_token(token)
        if payload:
            return payload.get("jti")
        return None

    def get_scope_from_token(self, token: str) -> Optional[str]:
        """
        Extrai o escopo do token.

        Args:
            token: Token JWT

        Returns:
            Escopo (GENERAL_USE, SET_PASSWORD, etc.) ou None
        """
        payload = self.verify_token(token)
        if payload:
            return payload.get("scope")
        return None

    def hash_password(self, password: str) -> str:
        """
        Hash de senha usando BCrypt.

        Args:
            password: Senha em texto puro

        Returns:
            Senha hasheada
        """
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verifica se a senha corresponde ao hash.

        Args:
            plain_password: Senha em texto puro
            hashed_password: Senha hasheada

        Returns:
            True se as senhas correspondem
        """
        return self.pwd_context.verify(plain_password, hashed_password)


jwt_manager = JWTManager()
