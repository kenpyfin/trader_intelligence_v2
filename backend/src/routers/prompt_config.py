"""API for viewing and editing GPT / LLM prompt templates."""
import asyncio
import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import prompt_config_service


router = APIRouter(tags=["Prompt Config"])


class PromptUpdateRequest(BaseModel):
    text: str = Field(..., description="Full prompt template text")


@router.get("/config/prompts")
@router.get("/api/config/prompts")
async def get_prompts():
    try:
        loop = asyncio.get_running_loop()
        prompts = await loop.run_in_executor(None, prompt_config_service.list_prompts)
        categories = prompt_config_service.list_categories()
        return {
            "status": "success",
            "prompts": prompts,
            "categories": categories,
        }
    except Exception as exc:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to list prompts: {exc}")


@router.post("/config/prompts/reset-all")
@router.post("/api/config/prompts/reset-all")
async def reset_all_prompts():
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, prompt_config_service.reset_all_prompts)
        return {
            "status": "success",
            "message": "All prompts reset to defaults",
            "prompts": result["prompts"],
            "persisted": result["persisted"],
        }
    except Exception as exc:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to reset prompts: {exc}")


@router.get("/config/prompts/{prompt_id}")
@router.get("/api/config/prompts/{prompt_id}")
async def get_prompt(prompt_id: str):
    try:
        loop = asyncio.get_running_loop()
        prompt = await loop.run_in_executor(
            None, lambda: prompt_config_service.serialize_prompt(prompt_id)
        )
        return {"status": "success", "prompt": prompt}
    except prompt_config_service.UnknownPromptError:
        raise HTTPException(status_code=404, detail=f"Unknown prompt id: {prompt_id}")
    except Exception as exc:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch prompt: {exc}")


@router.put("/config/prompts/{prompt_id}")
@router.put("/api/config/prompts/{prompt_id}")
async def put_prompt(prompt_id: str, request: PromptUpdateRequest):
    try:
        loop = asyncio.get_running_loop()
        prompt = await loop.run_in_executor(
            None, lambda: prompt_config_service.update_prompt(prompt_id, request.text)
        )
        return {
            "status": "success",
            "message": "Prompt saved",
            "prompt": prompt,
        }
    except prompt_config_service.UnknownPromptError:
        raise HTTPException(status_code=404, detail=f"Unknown prompt id: {prompt_id}")
    except prompt_config_service.PromptValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save prompt: {exc}")


@router.post("/config/prompts/{prompt_id}/reset")
@router.post("/api/config/prompts/{prompt_id}/reset")
async def reset_one_prompt(prompt_id: str):
    try:
        loop = asyncio.get_running_loop()
        prompt = await loop.run_in_executor(
            None, lambda: prompt_config_service.reset_prompt(prompt_id)
        )
        return {
            "status": "success",
            "message": "Prompt reset to default",
            "prompt": prompt,
        }
    except prompt_config_service.UnknownPromptError:
        raise HTTPException(status_code=404, detail=f"Unknown prompt id: {prompt_id}")
    except Exception as exc:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to reset prompt: {exc}")
