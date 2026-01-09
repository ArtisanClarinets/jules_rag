from __future__ import annotations

from typing import Optional, Set
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM Settings
    llm_provider: str = Field("openai", validation_alias="LLM_PROVIDER", pattern="^(openai|openrouter|local)$")
    llm_base_url: Optional[str] = Field(None, validation_alias="LLM_BASE_URL")
    llm_api_key: Optional[SecretStr] = Field(None, validation_alias="LLM_API_KEY")
    llm_model: str = Field("gpt-4o-mini", validation_alias="LLM_MODEL")
    llm_temperature: float = Field(0.0, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(2048, validation_alias="LLM_MAX_TOKENS")
    llm_prefer_json: bool = Field(True, validation_alias="LLM_PREFER_JSON")

    # OpenRouter Specific
    openrouter_api_key: Optional[SecretStr] = Field(None, validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field("https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL")
    openrouter_http_referer: Optional[str] = Field(None, validation_alias="OPENROUTER_HTTP_REFERER")
    openrouter_x_title: Optional[str] = Field(None, validation_alias="OPENROUTER_X_TITLE")

    # OpenAI Specific
    openai_api_key: Optional[SecretStr] = Field(None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL")

    # Embeddings Settings
    embeddings_provider: Optional[str] = Field(None, validation_alias="EMBEDDINGS_PROVIDER")
    embeddings_model: str = Field("openai/text-embedding-3-small", validation_alias="EMBEDDINGS_MODEL")
    embeddings_batch_size: int = Field(64, validation_alias="EMBEDDINGS_BATCH_SIZE")

    # Privacy & Limits
    rag_allow_globs: Set[str] = Field(default_factory=set, validation_alias="RAG_ALLOW_GLOBS")
    rag_deny_globs: Set[str] = Field(default_factory=set, validation_alias="RAG_DENY_GLOBS")
    rag_max_file_mb: int = Field(2, validation_alias="RAG_MAX_FILE_MB")  # Default 2MB
    rag_max_tokens_context: int = Field(8000, validation_alias="RAG_MAX_TOKENS_CONTEXT")
    rag_send_code_to_remote: bool = Field(False, validation_alias="RAG_SEND_CODE_TO_REMOTE")

    # Storage
    db_path: str = Field("codegraph.db", validation_alias="DB_PATH")

    # API Security
    rag_api_token: Optional[SecretStr] = Field(None, validation_alias="RAG_API_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_llm_api_key(self) -> SecretStr | None:
        if self.llm_provider == "openrouter":
            return self.openrouter_api_key or self.llm_api_key
        return self.openai_api_key or self.llm_api_key

    def get_llm_base_url(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider == "openrouter":
            return self.openrouter_base_url
        return self.openai_base_url

    def get_embeddings_provider(self) -> str:
        return self.embeddings_provider or self.llm_provider

# Global settings instance
settings = Settings()
