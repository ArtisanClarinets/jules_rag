from __future__ import annotations

import os
import yaml
from typing import Optional, Set, List, Dict, Any, Tuple
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

def yaml_config_settings_source() -> Dict[str, Any]:
    """
    A simple settings source that loads variables from a YAML file
    at the project's root.
    """
    yaml_file = "rag_config.yaml"
    if not os.path.exists(yaml_file):
        return {}

    try:
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

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

    # Retrieval Settings
    retrieval_k: int = Field(10, validation_alias="RETRIEVAL_K")
    retrieval_mmr_lambda: float = Field(0.5, validation_alias="RETRIEVAL_MMR_LAMBDA")
    retrieval_max_chunks_per_file: int = Field(5, validation_alias="RETRIEVAL_MAX_CHUNKS_PER_FILE")
    retrieval_enable_ann: bool = Field(True, validation_alias="RETRIEVAL_ENABLE_ANN")

    # Indexing Settings
    rag_allow_globs: Set[str] = Field(default_factory=set, validation_alias="RAG_ALLOW_GLOBS")
    rag_deny_globs: Set[str] = Field(default_factory=set, validation_alias="RAG_DENY_GLOBS")
    rag_max_file_mb: int = Field(2, validation_alias="RAG_MAX_FILE_MB")
    rag_max_tokens_context: int = Field(8000, validation_alias="RAG_MAX_TOKENS_CONTEXT")
    rag_send_code_to_remote: bool = Field(False, validation_alias="RAG_SEND_CODE_TO_REMOTE")

    # Next.js Specific Defaults
    next_ignore_dirs: Set[str] = Field(
        default_factory=lambda: {'.next', 'node_modules', 'dist', 'build', '.turbo', 'coverage'},
        validation_alias="NEXT_IGNORE_DIRS"
    )

    # Storage
    db_path: str = Field("codegraph.db", validation_alias="DB_PATH")

    # API Security
    rag_api_token: Optional[SecretStr] = Field(None, validation_alias="RAG_API_TOKEN") # Legacy single token
    rag_api_keys: List[SecretStr] = Field(default_factory=list, validation_alias="RAG_API_KEYS") # Comma separated
    rag_allowed_roots: List[str] = Field(default_factory=list, validation_alias="RAG_ALLOWED_ROOTS")
    rag_redact_secrets: bool = Field(True, validation_alias="RAG_REDACT_SECRETS")
    rag_allow_external_llm: bool = Field(True, validation_alias="RAG_ALLOW_EXTERNAL_LLM")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_config_settings_source,
            file_secret_settings,
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
