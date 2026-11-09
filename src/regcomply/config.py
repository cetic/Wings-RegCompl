from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    local_llm_model: str = "gemma4:4b"
    gemini_model: str = "gemini-3-flash-preview"
    extraction_max_unit_chars: int = 1500


settings = Settings()
