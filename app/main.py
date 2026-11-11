from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="gostrag", version=settings.app_version)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": settings.app_version,
        "corpus_version": settings.corpus_version,
    }
