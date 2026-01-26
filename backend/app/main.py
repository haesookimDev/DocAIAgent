"""FastAPI Application Entry Point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from app.config import get_settings
from app.api import runs, artifacts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    # Create storage directory
    storage_path = Path(settings.storage_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "artifacts").mkdir(exist_ok=True)
    (storage_path / "uploads").mkdir(exist_ok=True)

    print(f"DocAIAgent Backend starting...")
    print(f"Storage path: {storage_path.absolute()}")
    print(f"Default LLM: {settings.default_llm_provider}")

    yield

    print("DocAIAgent Backend shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="DocAIAgent API",
        description="AI-powered document generation agent API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    app.include_router(runs.router, prefix="/api/v1", tags=["runs"])
    app.include_router(artifacts.router, prefix="/api/v1", tags=["artifacts"])

    # Static files for test UI
    static_path = Path(__file__).parent.parent / "static"
    print(f"Static path: {static_path.absolute()}")
    print(f"Static path exists: {static_path.exists()}")

    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

        @app.get("/")
        async def root():
            """Redirect to UI."""
            return RedirectResponse(url="/static/index.html")

        @app.get("/ui")
        async def ui():
            """Serve the UI directly."""
            index_path = static_path / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return {"error": "UI not found"}
    else:
        @app.get("/")
        async def root():
            """Root endpoint - API info."""
            return {
                "name": "DocAIAgent API",
                "version": "0.1.0",
                "docs": "/docs",
                "note": "Static UI not found. Run from backend directory.",
            }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
