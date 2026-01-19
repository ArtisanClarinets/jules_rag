from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, RedisDsn
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Vantus Vector Platform"
    API_V1_STR: str = "/api/v1"

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432

    REDIS_HOST: str
    REDIS_PASSWORD: str
    REDIS_PORT: int = 6379

    QDRANT_HOST: str
    QDRANT_PORT: int = 6333

    OPENSEARCH_HOST: str
    OPENSEARCH_PASSWORD: str
    OPENSEARCH_PORT: int = 9200

    MINIO_ENDPOINT: str
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str

    JWT_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days

    WORKER_CONCURRENCY: int = 4

    # Defaults
    EMBEDDING_PROVIDER: str = "local_cpu"
    RERANK_PROVIDER: str = "local_cpu"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

settings = Settings()
