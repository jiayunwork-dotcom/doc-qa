import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "DocQA Platform"
    DEBUG: bool = True

    DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    UPLOAD_DIR: str = os.path.join(DATA_DIR, "uploads")
    INDEX_DIR: str = os.path.join(DATA_DIR, "indexes")
    DB_PATH: str = os.path.join(DATA_DIR, "docqa.db")

    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = 384
    RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    LLM_MODE: str = os.getenv("LLM_MODE", "local")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "Qwen/Qwen2-0.5B-Instruct")
    REMOTE_API_KEY: str = os.getenv("REMOTE_API_KEY", "")
    REMOTE_API_ENDPOINT: str = os.getenv("REMOTE_API_ENDPOINT", "https://api.openai.com/v1")
    REMOTE_MODEL_NAME: str = os.getenv("REMOTE_MODEL_NAME", "gpt-3.5-turbo")

    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    MAX_DOCS_PER_KB: int = 100

    DEFAULT_CHUNK_STRATEGY: str = "fixed"
    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 100
    DEFAULT_TOP_K: int = 20
    DEFAULT_TOP_N: int = 5
    MMR_LAMBDA: float = 0.7

    IVF_THRESHOLD: int = 10000

    CORS_ORIGINS: list = ["*"]

    class Config:
        env_file = ".env"


settings = Settings()

os.makedirs(settings.DATA_DIR, exist_ok=True)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.INDEX_DIR, exist_ok=True)
