from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # OpenAI settings
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4.1-mini"
    
    # Database settings
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    
    # Admin credentials
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str
    ADMIN_SECRET_KEY: str
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = True
    LOG_DIR: str = "logs"
    
    # Environment
    ENVIRONMENT: str = "development"  # development, staging, production

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"  # Changed from forbid to ignore for flexibility
    )


settings = Settings()
