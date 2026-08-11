from typing import Any

from comfy_helper.domain.models import Artifact, JobProgress, JobStatus
from comfy_helper.providers.base import (
    GenerationProvider,
    ProviderArtifactContent,
    ProviderHealth,
    ProviderJobSnapshot,
    ProviderSubmission,
)


class FakeProvider(GenerationProvider):
    name = "comfyui"

    def __init__(self) -> None:
        self.submitted_workflow: dict[str, Any] | None = None
        self.cancelled_ids: list[str] = []
        self._status = JobStatus.succeeded
        self._progress = JobProgress(value=10, max=10, percent=100.0)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, status="ok", version="test")

    async def submit(
        self, workflow: dict[str, Any], client_id: str
    ) -> ProviderSubmission:
        self.submitted_workflow = workflow
        self._status = JobStatus.running
        self._progress = JobProgress(value=1, max=10, node="5", percent=10.0)
        return ProviderSubmission(id="provider-job-1", queue_number=1)

    async def get_job(self, provider_job_id: str) -> ProviderJobSnapshot:
        if self._status is JobStatus.running:
            # First refresh transitions to success with artifacts.
            self._status = JobStatus.succeeded
            self._progress = JobProgress(value=10, max=10, percent=100.0)
            return ProviderJobSnapshot(
                status=JobStatus.succeeded,
                progress=self._progress,
                artifacts=[
                    Artifact(
                        filename="generated.png",
                        source_url="http://comfy/view?filename=generated.png",
                    )
                ],
            )
        return ProviderJobSnapshot(
            status=self._status,
            progress=self._progress,
            artifacts=(
                [
                    Artifact(
                        filename="generated.png",
                        source_url="http://comfy/view?filename=generated.png",
                    )
                ]
                if self._status is JobStatus.succeeded
                else []
            ),
        )

    async def cancel(self, provider_job_id: str) -> None:
        self.cancelled_ids.append(provider_job_id)
        self._status = JobStatus.cancelled
        self._progress = JobProgress(value=1, max=10, percent=10.0)

    async def model_inventory(self) -> dict[str, list[str]]:
        return {"diffusion_models": ["anima-turbo-v1.0.safetensors"]}

    async def download_artifact(self, artifact: Artifact) -> ProviderArtifactContent:
        return ProviderArtifactContent(
            content=b"generated-image", content_type="image/png"
        )
