from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=(".env", "deploy/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # GigaChat
    gigachat_credentials: str = Field(default="", alias="GIGACHAT_CREDENTIALS")
    gigachat_scope: str = Field(default="GIGACHAT_API_PERS", alias="GIGACHAT_SCOPE")
    gigachat_base_url: str = Field(default="https://api.giga.chat/v1", alias="GIGACHAT_BASE_URL")
    gigachat_auth_url: str = Field(
        default="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        alias="GIGACHAT_AUTH_URL",
    )
    gigachat_model_ultra: str = Field(default="GigaChat-3-Ultra", alias="GIGACHAT_MODEL_ULTRA")
    gigachat_model_max: str = Field(default="GigaChat-2-Max", alias="GIGACHAT_MODEL_MAX")
    gigachat_model_pro: str = Field(default="GigaChat-2-Pro", alias="GIGACHAT_MODEL_PRO")
    gigachat_model_lite: str = Field(default="GigaChat-2", alias="GIGACHAT_MODEL_LITE")
    gigachat_embedding_model: str = Field(
        default="GigaEmbeddings-3B-2025-09", alias="GIGACHAT_EMBEDDING_MODEL"
    )
    gigachat_embedding_dim: int = Field(default=2048, alias="GIGACHAT_EMBEDDING_DIM")
    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    embedding_cache_dir: str = Field(default="", alias="EMBEDDING_CACHE_DIR")
    embedding_threads: int = Field(default=0, alias="EMBEDDING_THREADS")

    # Yandex AI Studio fallback
    yc_folder_id: str = Field(default="", alias="YC_FOLDER_ID")
    yc_api_key: str = Field(default="", alias="YC_API_KEY")
    yc_model: str = Field(default="deepseek-v4.1-flash/latest", alias="YC_MODEL")
    yc_base_url: str = Field(default="https://ai.api.cloud.yandex.net/v1", alias="YC_BASE_URL")

    # Direct DeepSeek fallback
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-flash", alias="DEEPSEEK_MODEL")

    # S3 / Object Storage
    s3_endpoint: str = Field(default="https://storage.yandexcloud.net", alias="S3_ENDPOINT")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_access_key: str = Field(default="", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="S3_SECRET_KEY")
    s3_region: str = Field(default="ru-central1", alias="S3_REGION")
    s3_prefix: str = Field(default="gost/", alias="S3_PREFIX")

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_user_ids: str = Field(default="", alias="TELEGRAM_USER_IDS")
    telegram_admin_ids: str = Field(default="", alias="TELEGRAM_ADMIN_IDS")

    # Infra
    postgres_dsn: str = Field(
        default="postgresql://gostrag:gostrag@postgres:5432/gostrag", alias="POSTGRES_DSN"
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    qdrant_url: str = Field(default="http://qdrant:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="gost_chunks", alias="QDRANT_COLLECTION")

    # Limits
    daily_questions_per_user: int = Field(default=50, alias="DAILY_QUESTIONS_PER_USER")
    hourly_questions_per_user: int = Field(default=10, alias="HOURLY_QUESTIONS_PER_USER")
    daily_tokens_global: int = Field(default=2_000_000, alias="DAILY_TOKENS_GLOBAL")
    max_top_k: int = Field(default=10, alias="MAX_TOP_K")
    request_timeout_sec: int = Field(default=90, alias="REQUEST_TIMEOUT_SEC")
    queue_max_depth: int = Field(default=5, alias="QUEUE_MAX_DEPTH")

    # App
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    corpus_version: str = Field(default="2026.11.11", alias="CORPUS_VERSION")
    data_source_dir: str = Field(default="/data/source", alias="DATA_SOURCE_DIR")
    data_corpus_dir: str = Field(default="/data/corpus", alias="DATA_CORPUS_DIR")
    reports_dir: str = Field(default="/app/reports", alias="REPORTS_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def allowed_user_ids(self) -> set[int]:
        return {int(x) for x in self.telegram_user_ids.replace(" ", "").split(",") if x}

    @property
    def admin_user_ids(self) -> set[int]:
        return {int(x) for x in self.telegram_admin_ids.replace(" ", "").split(",") if x}


@lru_cache
def get_settings() -> Settings:
    return Settings()
