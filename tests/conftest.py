import httpx
import pytest

from comfy_helper.api import create_app
from comfy_helper.config import Settings
from tests.fakes import FakeProvider


@pytest.fixture
async def client_and_provider(tmp_path):
    provider = FakeProvider()
    settings = Settings(
        artifact_dir=tmp_path / "artifacts", database_path=tmp_path / "test.db"
    )
    transport = httpx.ASGITransport(
        app=create_app(settings=settings, provider=provider)
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, provider
