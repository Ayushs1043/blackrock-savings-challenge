from fastapi import FastAPI

from app.api.routes import router
from app.errors import add_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="BlackRock Hackathon API",
        version="1.0.0",
        description="Template API to transform, validate, and calculate financial returns.",
    )
    app.include_router(router)
    add_exception_handlers(app)
    return app


app = create_app()
