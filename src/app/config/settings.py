from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str
    llm_model: str
    anonymization_key: str = "1111222233334444"
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_validity: int = 3600  # 1 hora em segundos
    jwt_refresh_validity: int = 86400  # 24 horas em segundos (igual ao Backend Java)
    cookie_secure: bool = False  # Igual ao Backend Java (false em dev, true em prod)

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()