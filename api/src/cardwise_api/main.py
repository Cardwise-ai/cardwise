"""Application factory. Vercel imports the module-level `app`."""

from fastapi import FastAPI

from cardwise_api.errors import install_error_handling
from cardwise_api.routes import public, v1


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cardwise API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    install_error_handling(app)
    app.include_router(public)
    app.include_router(v1)
    return app


app = create_app()
