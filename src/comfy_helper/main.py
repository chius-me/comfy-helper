import uvicorn

from comfy_helper.config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "comfy_helper.api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
