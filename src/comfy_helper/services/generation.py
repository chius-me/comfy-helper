from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from comfy_helper.domain.models import (
    Artifact,
    GenerationJob,
    GenerationRequest,
    JobStatus,
)
from comfy_helper.providers.base import GenerationProvider
from comfy_helper.services.artifacts import ArtifactNotFoundError, ArtifactStore
from comfy_helper.services.repository import SqliteJobRepository
from comfy_helper.workflows.registry import WorkflowRegistry


class JobNotFoundError(KeyError):
    pass


class JobNotCancellableError(RuntimeError):
    pass


class GenerationService:
    def __init__(
        self,
        provider: GenerationProvider,
        registry: WorkflowRegistry,
        artifact_store: ArtifactStore,
        repository: SqliteJobRepository | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._artifact_store = artifact_store
        self._repository = repository
        self._jobs: dict[UUID, GenerationJob] = {}

    async def create(self, request: GenerationRequest) -> GenerationJob:
        profile = self._registry.get(request.profile_id)
        workflow = profile.render(request.workflow_parameters())
        client_id = str(uuid4())
        submission = await self._provider.submit(workflow, client_id)
        job = GenerationJob(
            provider=self._provider.name,
            provider_job_id=submission.id,
            client_id=client_id,
            profile_id=profile.id,
            request=request,
        )
        self._jobs[job.id] = job
        self._persist(job)
        return job

    async def get(self, job_id: UUID, refresh: bool = True) -> GenerationJob:
        job = await self._load_job(job_id)
        terminal = {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}
        if refresh and job.status not in terminal:
            snapshot = await self._provider.get_job(job.provider_job_id)
            if snapshot.status is JobStatus.succeeded:
                snapshot.artifacts = await self._store_artifacts(
                    job, snapshot.artifacts
                )
            job.status = snapshot.status
            job.artifacts = snapshot.artifacts
            job.error = snapshot.error
            job.progress = snapshot.progress
            job.updated_at = datetime.now(UTC)
            self._persist(job)
        return job

    async def cancel(self, job_id: UUID) -> GenerationJob:
        job = await self._load_job(job_id)
        terminal = {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}
        if job.status in terminal:
            raise JobNotCancellableError(f"job already {job.status.value}")
        await self._provider.cancel(job.provider_job_id)
        job.status = JobStatus.cancelled
        job.error = None
        job.updated_at = datetime.now(UTC)
        self._persist(job)
        return job

    async def stream_events(
        self, job_id: UUID, *, poll_interval: float = 0.5
    ) -> AsyncIterator[str]:
        """Yield SSE payloads until the job reaches a terminal state."""
        while True:
            job = await self.get(job_id, refresh=True)
            payload = job.model_dump(mode="json")
            yield f"event: job\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
            if job.status in {
                JobStatus.succeeded,
                JobStatus.failed,
                JobStatus.cancelled,
            }:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(poll_interval)

    async def _load_job(self, job_id: UUID) -> GenerationJob:
        job = self._jobs.get(job_id)
        if job is None and self._repository is not None:
            job = self._repository.get_job(job_id)
            if job is not None:
                for artifact in job.artifacts:
                    self._artifact_store.register(artifact)
                self._jobs[job.id] = job
        if job is None:
            raise JobNotFoundError(str(job_id))
        return job

    async def _store_artifacts(
        self, job: GenerationJob, artifacts: list[Artifact]
    ) -> list[Artifact]:
        stored: list[Artifact] = []
        for artifact in artifacts:
            content = await self._provider.download_artifact(artifact)
            stored.append(self._artifact_store.store(job.id, artifact, content))
        return stored

    def get_artifact(self, artifact_id: UUID) -> Artifact:
        try:
            return self._artifact_store.get(artifact_id)
        except ArtifactNotFoundError:
            if self._repository is None:
                raise
            artifact = self._repository.get_artifact(artifact_id)
            if artifact is None:
                raise ArtifactNotFoundError(str(artifact_id))
            return self._artifact_store.register(artifact)

    def _persist(self, job: GenerationJob) -> None:
        if self._repository is not None:
            self._repository.save_job(job)
