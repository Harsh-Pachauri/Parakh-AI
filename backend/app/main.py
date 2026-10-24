"""FastAPI application initialization and core routes."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import api_router
from app.config import get_settings
from app.database import get_db
from app.llm.groq import GroqProvider, GroqRequestError

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown routines."""
    current_settings = get_settings()
    if current_settings.SECRET_KEY == "temporary-dev-secret-key-change-in-production-12345" and (
        not current_settings.DEBUG or current_settings.ENVIRONMENT.lower() == "production"
    ):
        import logging

        logging.getLogger("uvicorn.error").warning(
            "CRITICAL SECURITY WARNING: Application is running with the default development SECRET_KEY. "
            "Please generate and set a strong, unique SECRET_KEY in your environment for production deployments."
        )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Automated oral examination system backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/api/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Health check endpoint that verifies API liveness and database connectivity."""
    try:
        result = await db.execute(text("SELECT 1"))
        _ = result.scalar()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {exc}",
        ) from exc

    return {"status": "ok", "db": "connected", "message": "Hello, Viva!"}


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint welcoming visitors to the Viva Voce API."""
    return {
        "app": settings.APP_NAME,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health/ai", tags=["Health"])
async def ai_health_check() -> dict[str, str]:
    """Verify that the configured Groq model can complete a real request."""
    try:
        await GroqProvider().generate("Reply with the single word READY.")
    except GroqRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"status": "ok", "provider": "groq", "model": settings.GROQ_MODEL}
