"""FastAPI application for PredUp"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import iterate_in_threadpool
import json


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

    # CORS for production
    frontend_url = get_env_var("FRONTEND_URL", "https://predup-web.vercel.app")
    allowed_origins = [
        frontend_url,
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": "Internal Server Error",
                "data": None,
                "meta": {}
            }
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": str(exc.detail),
                "data": None,
                "meta": {}
            }
        )

    @app.middleware("http")
    async def wrap_response(request: Request, call_next):
        response = await call_next(request)
        
        # Only wrap if it's a JSON response and in the /api/v1 path
        content_type = response.headers.get("content-type", "")
        if (request.url.path.startswith("/api/v1") and "application/json" in content_type):
            try:
                # Standard FastAPI call_next returns a StreamingResponse
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                
                # We must reset the iterator so the response can still be sent if we don't return a new one
                response.body_iterator = iterate_in_threadpool(iter([body]))
                
                if not body:
                    return response
                    
                data = json.loads(body.decode())
                
                # Check if already wrapped
                if isinstance(data, dict) and "status" in data and ("data" in data or "error" in data):
                    return response
                
                wrapped = {
                    "status": "success",
                    "data": data,
                    "meta": {}
                }
                
                return JSONResponse(
                    content=wrapped,
                    status_code=response.status_code,
                    headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"}
                )
            except Exception as e:
                logger.error(f"Error wrapping response: {e}")
                return response
        
        return response

    from src.api.routes import router
    
    # Initialize router state
    router.state = type('State', (), {})()
    router.state.registry = None
    router.state.calibrator_loaded = False
    router.state.calibrator_info = {"status": "not_loaded"}
    
    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health_check():
        return {"status": "success", "data": {"status": "healthy", "service": "predup"}, "meta": {}}

    @app.get("/")
    async def root():
        return {
            "status": "success",
            "data": {
                "service": "PredUp",
                "version": "0.1.0",
                "docs": "/docs"
            },
            "meta": {}
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(get_env_var("PORT", 8000))
    host = get_env_var("HOST", "0.0.0.0")

    uvicorn.run(app, host=host, port=port)