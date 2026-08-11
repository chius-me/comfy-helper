from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from comfy_helper.domain.models import Artifact, JobProgress, JobStatus


class ProviderHealth(BaseModel):
    name: str
    status: str
    detail: str | None = None
    version: str | None = None


class ProviderSubmission(BaseModel):
    id: str
    queue_number: int | None = None


class ProviderArtifactContent(BaseModel):
    content: bytes
    content_type: str = "application/octet-stream"


class ProviderJobSnapshot(BaseModel):
    status: JobStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    error: str | None = None
    progress: JobProgress | None = None


class GenerationProvider(ABC):
    name: str

    @abstractmethod
    async def health(self) -> ProviderHealth: ...

    @abstractmethod
    async def submit(
        self, workflow: dict[str, Any], client_id: str
    ) -> ProviderSubmission: ...

    @abstractmethod
    async def get_job(self, provider_job_id: str) -> ProviderJobSnapshot: ...

    @abstractmethod
    async def model_inventory(self) -> dict[str, list[str]]: ...

    @abstractmethod
    async def download_artifact(
        self, artifact: Artifact
    ) -> ProviderArtifactContent: ...

    async def cancel(self, provider_job_id: str) -> None:
        raise NotImplementedError(f"{self.name} does not support cancellation")

    async def close(self) -> None:
        return None
