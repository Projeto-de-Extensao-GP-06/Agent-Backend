from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str
    llm_model: str
    anonymization_key: str = "1111222233334444"
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_validity: int = 3600  # 1 hora em segundos
    jwt_refresh_validity: int = 604800  # 7 dias em segundos

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()