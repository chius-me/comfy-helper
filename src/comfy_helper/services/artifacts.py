import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from comfy_helper.domain.models import Artifact
from comfy_helper.providers.base import ProviderArtifactContent


class ArtifactNotFoundError(KeyError):
    pass


class ArtifactTooLargeError(ValueError):
    pass


class ArtifactStore:
    def __init__(self, root: Path, max_bytes: int = 50 * 1024 * 1024) -> None:
        self._root = root.resolve()
        self._max_bytes = max_bytes
        self._artifacts: dict[UUID, Artifact] = {}
        self._root.mkdir(parents=True, exist_ok=True)

    def register(self, artifact: Artifact) -> Artifact:
        """Register metadata recovered from durable storage."""
        self._artifacts[artifact.id] = artifact
        return artifact

    def store(
        self,
        job_id: UUID,
        artifact: Artifact,
        content: ProviderArtifactContent,
    ) -> Artifact:
        if len(content.content) > self._max_bytes:
            raise ArtifactTooLargeError(
                f"artifact exceeds max size of {self._max_bytes} bytes"
            )

        suffix = Path(artifact.filename).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ".bin"
        directory = self._root / str(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{artifact.id}{suffix}"
        self._atomic_write(path, content.content)

        artifact.local_path = str(path)
        artifact.content_type = content.content_type
        artifact.size_bytes = len(content.content)
        artifact.url = f"/api/v1/artifacts/{artifact.id}"
        self._artifacts[artifact.id] = artifact
        return artifact

    def get(self, artifact_id: UUID) -> Artifact:
        try:
            return self._artifacts[artifact_id]
        except KeyError as exc:
            raise ArtifactNotFoundError(str(artifact_id)) from exc

    def _atomic_write(self, path: Path, content: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".partial",
            dir=path.parent,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
