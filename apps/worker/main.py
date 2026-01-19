from arq.connections import RedisSettings
from apps.api.core.config import settings
from apps.worker.tasks import ingest_repo, ingest_doc
import sys

# Add root to path
sys.path.append(".")

class WorkerSettings:
    functions = [ingest_repo, ingest_doc]
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD
    )
    max_jobs = settings.WORKER_CONCURRENCY
