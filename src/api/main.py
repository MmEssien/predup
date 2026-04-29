"""FastAPI application for PredUp"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.data.connection import DatabaseManager, db_manager
from src.models.registry import create_registry
from src.utils.helpers import load_config, get_env_var

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting PredUp API...")

    config = load_config()

    db_manager.initialize()
    logger.info("Database initialized")

    app.state.registry = create_registry("models")
    logger.info("Model registry loaded")

    yield

    db_manager.close()
    logger.info("Shutting down PredUp API...")


def create_app() -> FastAPI:
    config = load_config()
    app_config = config.get("app", {})

    app = FastAPI(
        title="PredUp API",
        description="Sports Intelligence API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for production - allow Vercel frontend and localhost
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://predup.vercel.app",
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routes import router
    
    # Initialize router state
    router.state = type('State', (), {})()
    router.state.registry = None
    router.state.calibrator_loaded = False
    router.state.calibrator_info = {"status": "not_loaded"}
    
    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "predup"}

    @app.get("/")
    async def root():
        return {
            "service": "PredUp",
            "version": "0.1.0",
            "docs": "/docs"
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(get_env_var("PORT", 8000))
    host = get_env_var("HOST", "0.0.0.0")

    uvicorn.run(app, host=host, port=port)