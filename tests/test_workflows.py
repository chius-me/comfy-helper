from comfy_helper.domain.models import GenerationRequest, JobStatus
from comfy_helper.workflows.registry import get_default_registry


def test_anima_profile_renders_runnable_api_workflow() -> None:
    profile = get_default_registry().get("anima-turbo-t2i")

    workflow = profile.render(
        {
            "prompt": "1girl, blue hair",
            "negative_prompt": "low quality",
            "width": 768,
            "height": 1024,
            "seed": 123,
            "steps": 8,
            "cfg": 1.2,
        }
    )

    assert workflow["1"]["inputs"]["unet_name"] == "anima-turbo-v1.0.safetensors"
    assert workflow["2"]["inputs"]["clip_name"] == "qwen_3_06b_base.safetensors"
    assert workflow["4"]["inputs"]["text"] == "1girl, blue hair"
    assert workflow["5"]["inputs"]["text"] == "low quality"
    assert workflow["6"]["inputs"] == {"width": 768, "height": 1024, "batch_size": 1}
    assert workflow["7"]["inputs"]["seed"] == 123
    assert workflow["7"]["inputs"]["steps"] == 8
    assert workflow["7"]["inputs"]["cfg"] == 1.2
    assert workflow["9"]["class_type"] == "SaveImage"


def test_wai_profile_renders_sdxl_checkpoint_api_workflow() -> None:
    profile = get_default_registry().get("wai-illustrious-t2i")

    workflow = profile.render(
        {
            "prompt": "1girl, masterpiece",
            "negative_prompt": "low quality",
            "width": 1024,
            "height": 1024,
            "seed": 7,
            "steps": 24,
            "cfg": 4.5,
        }
    )

    assert profile.model_family == "wai"
    assert workflow["1"]["class_type"] == "CheckpointLoaderSimple"
    assert workflow["1"]["inputs"]["ckpt_name"] == "waiNSFWIllustrious_v150.safetensors"
    assert workflow["2"]["inputs"]["text"] == "1girl, masterpiece"
    assert workflow["3"]["inputs"]["text"] == "low quality"
    assert workflow["4"]["inputs"]["width"] == 1024
    assert workflow["5"]["inputs"]["seed"] == 7
    assert workflow["5"]["inputs"]["steps"] == 24
    assert workflow["5"]["inputs"]["cfg"] == 4.5
    assert workflow["7"]["class_type"] == "SaveImage"


def test_generation_request_and_job_status_are_typed() -> None:
    request = GenerationRequest(profile_id="anima-turbo-t2i", prompt="1girl")

    assert request.width == 1024
    assert request.height == 1024
    assert request.seed is None
    assert JobStatus.queued.value == "queued"
