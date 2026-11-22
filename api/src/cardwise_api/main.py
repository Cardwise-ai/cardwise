"""Application factory. Vercel imports the module-level `app` (see [tool.vercel] in pyproject)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cardwise_api.dependencies import Services
from cardwise_api.errors import REQUEST_ID_HEADER, RequestIdMiddleware, install_error_handling
from cardwise_api.observability import AccessLogMiddleware, configure_logging
from cardwise_api.routes import public, v1
from cardwise_api.security import SecurityHeadersMiddleware
from cardwise_api.settings import Settings


def create_app(settings: Settings | None = None, *, services: Services | None = None) -> FastAPI:
    if services is None:
        services = Services.from_settings(settings or Settings())
    settings = services.settings
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Cardwise API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None if settings.deployed else "/openapi.json",
    )
    app.state.services = services
    install_error_handling(app)
    app.include_router(public)
    app.include_router(v1)

    # Starlette runs the last-added middleware first. Request order, outermost first:
    # request ID -> access log -> security headers -> CORS -> routes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.web_origin),
        allow_origin_regex=settings.web_origin_regex,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
        allow_credentials=False,
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, force_hsts=settings.deployed)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


app = create_app()
