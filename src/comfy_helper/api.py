from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from comfy_helper.config import Settings, get_settings
from comfy_helper.domain.models import Artifact, GenerationJob, GenerationRequest
from comfy_helper.providers.base import GenerationProvider
from comfy_helper.providers.comfyui import ComfyUIProvider
from comfy_helper.services.artifacts import (
    ArtifactNotFoundError,
    ArtifactStore,
    ArtifactTooLargeError,
)
from comfy_helper.services.generation import (
    GenerationService,
    JobNotCancellableError,
    JobNotFoundError,
)
from comfy_helper.services.repository import SqliteJobRepository
from comfy_helper.workflows.profile import WorkflowProfile
from comfy_helper.workflows.registry import WorkflowRegistry, get_default_registry


def create_app(
    settings: Settings | None = None,
    provider: GenerationProvider | None = None,
    registry: WorkflowRegistry | None = None,
    repository: SqliteJobRepository | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    provider = provider or ComfyUIProvider(
        str(settings.comfyui_url),
        timeout=settings.comfyui_timeout_seconds,
        max_artifact_bytes=settings.max_artifact_bytes,
    )
    registry = registry or get_default_registry()
    artifact_store = ArtifactStore(
        settings.artifact_dir, max_bytes=settings.max_artifact_bytes
    )
    if repository is None:
        repository = SqliteJobRepository(settings.database_path)
    generation_service = GenerationService(
        provider, registry, artifact_store, repository=repository
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.provider = provider
        app.state.generation_service = generation_service
        app.state.repository = repository
        yield
        await provider.close()
        repository.close()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Gateway API for provider-neutral generative workflows.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        provider_health = await provider.health()
        return {
            "service": settings.app_name,
            "status": "ok" if provider_health.status == "ok" else "degraded",
            "provider": provider_health.model_dump(),
        }

    @app.get("/api/v1/providers")
    async def list_providers() -> list[dict[str, object]]:
        provider_health = await provider.health()
        try:
            models = await provider.model_inventory()
        except (httpx.HTTPError, ValueError):
            models = {}
        return [{**provider_health.model_dump(), "models": models}]

    @app.get("/api/v1/workflow-profiles", response_model=list[WorkflowProfile])
    async def list_workflow_profiles() -> list[WorkflowProfile]:
        return registry.list()

    @app.get("/api/v1/workflow-profiles/{profile_id}", response_model=WorkflowProfile)
    async def get_workflow_profile(profile_id: str) -> WorkflowProfile:
        try:
            return registry.get(profile_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/generations",
        response_model=GenerationJob,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_generation(request: GenerationRequest) -> GenerationJob:
        try:
            return await generation_service.create(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"provider submission failed: {exc}"
            ) from exc

    @app.get("/api/v1/jobs/{job_id}", response_model=GenerationJob)
    async def get_job(job_id: UUID) -> GenerationJob:
        try:
            return await generation_service.get(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ArtifactTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"provider status failed: {exc}"
            ) from exc

    @app.get("/api/v1/jobs/{job_id}/events")
    async def stream_job_events(job_id: UUID) -> StreamingResponse:
        try:
            await generation_service.get(job_id, refresh=False)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

        return StreamingResponse(
            generation_service.stream_events(job_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=GenerationJob)
    async def cancel_job(job_id: UUID) -> GenerationJob:
        try:
            return await generation_service.cancel(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except JobNotCancellableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"provider cancel failed: {exc}"
            ) from exc

    @app.get("/api/v1/jobs/{job_id}/artifacts", response_model=list[Artifact])
    async def list_job_artifacts(job_id: UUID) -> list[Artifact]:
        try:
            return (await generation_service.get(job_id)).artifacts
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ArtifactTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"provider status failed: {exc}"
            ) from exc

    @app.get("/api/v1/artifacts/{artifact_id}", response_class=FileResponse)
    async def get_artifact(artifact_id: UUID) -> FileResponse:
        try:
            artifact = generation_service.get_artifact(artifact_id)
        except ArtifactNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        if artifact.local_path is None:
            raise HTTPException(status_code=404, detail="artifact file not found")
        return FileResponse(
            artifact.local_path,
            media_type=artifact.content_type,
            filename=artifact.filename,
            content_disposition_type="inline",
        )

    return app


app = create_app()
