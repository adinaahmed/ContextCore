from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_api_key: str
    gemini_model: str = "gemini-3.6-flash"
    database_url: str
    jwt_secret_key: str
    api_key: str = "change-this-secret-key"

    chunk_size: int = 500
    chunk_overlap: int = 50
    default_chunk_strategy: str = "recursive"

    llm_provider: str = "gemini"
    llm_fallback_provider: str = "ollama"
    ollama_model: str = "gemma3:4b"
    ollama_base_url: str = "http://localhost:11434"

    embedding_provider: str = "local"
    vector_store_provider: str = "chroma"
    chroma_persist_directory: str = "./chroma_db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
