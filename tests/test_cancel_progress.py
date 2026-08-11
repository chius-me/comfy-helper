import json

import pytest


@pytest.mark.asyncio
async def test_cancel_job_marks_cancelled(client_and_provider) -> None:
    client, provider = client_and_provider
    created = await client.post(
        "/api/v1/generations",
        json={"profile_id": "anima-turbo-t2i", "prompt": "cancel me"},
    )
    job_id = created.json()["id"]

    # Keep the provider non-terminal before cancel.
    from comfy_helper.domain.models import JobStatus

    provider._status = JobStatus.running

    cancelled = await client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert provider.cancelled_ids == ["provider-job-1"]

    again = await client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_job_events_stream_includes_progress_and_terminal_event(
    client_and_provider,
) -> None:
    client, _ = client_and_provider
    created = await client.post(
        "/api/v1/generations",
        json={"profile_id": "anima-turbo-t2i", "prompt": "stream me"},
    )
    job_id = created.json()["id"]

    async with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
            if "event: done" in body:
                break

    assert "event: job" in body
    assert "event: done" in body
    blocks = [b for b in body.split("\n\n") if b.startswith("event: job")]
    assert blocks
    data_line = next(
        line for line in blocks[-1].splitlines() if line.startswith("data: ")
    )
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["status"] == "succeeded"
    assert payload["progress"]["percent"] == 100.0
