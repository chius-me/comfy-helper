from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

from comfy_helper.domain.models import Artifact, GenerationJob


class SqliteJobRepository:
    """Persist gateway jobs and artifact metadata for restart recovery."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            )
            """
        )
        self._conn.commit()

    def save_job(self, job: GenerationJob) -> None:
        payload = self._dump_job(job)
        self._conn.execute(
            """
            INSERT INTO jobs (id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (str(job.id), json.dumps(payload), job.updated_at.isoformat()),
        )
        self._conn.execute("DELETE FROM artifacts WHERE job_id = ?", (str(job.id),))
        for artifact in job.artifacts:
            self._conn.execute(
                """
                INSERT INTO artifacts (id, job_id, payload)
                VALUES (?, ?, ?)
                """,
                (
                    str(artifact.id),
                    str(job.id),
                    json.dumps(self._dump_artifact(artifact)),
                ),
            )
        self._conn.commit()

    def get_job(self, job_id: UUID) -> GenerationJob | None:
        row = self._conn.execute(
            "SELECT payload FROM jobs WHERE id = ?", (str(job_id),)
        ).fetchone()
        if row is None:
            return None
        return GenerationJob.model_validate(json.loads(row["payload"]))

    def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        row = self._conn.execute(
            "SELECT payload FROM artifacts WHERE id = ?", (str(artifact_id),)
        ).fetchone()
        if row is None:
            return None
        return Artifact.model_validate(json.loads(row["payload"]))

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _dump_job(job: GenerationJob) -> dict:
        payload = job.model_dump(mode="json")
        payload["provider_job_id"] = job.provider_job_id
        payload["client_id"] = job.client_id
        payload["artifacts"] = [
            SqliteJobRepository._dump_artifact(artifact) for artifact in job.artifacts
        ]
        return payload

    @staticmethod
    def _dump_artifact(artifact: Artifact) -> dict:
        payload = artifact.model_dump(mode="json")
        payload["source_url"] = artifact.source_url
        payload["local_path"] = artifact.local_path
        return payload
