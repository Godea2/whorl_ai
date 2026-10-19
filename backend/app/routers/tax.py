from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.auth.dependencies import CurrentUser
from app.models.tax import (
    TaxClassificationPatch,
    TaxClassifyRequest,
    TaxProfileUpsert,
    TaxReturnGenerateRequest,
    TaxReturnStatusUpdate,
)
from app.services import tax_service

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/framework")
async def tax_framework(_: CurrentUser) -> dict[str, Any]:
    return await tax_service.framework_info()


@router.get("/profile")
async def get_profile(user_id: CurrentUser) -> dict[str, Any]:
    return await tax_service.get_or_create_profile(user_id)


@router.put("/profile")
async def put_profile(user_id: CurrentUser, body: TaxProfileUpsert) -> dict[str, Any]:
    return await tax_service.upsert_profile(user_id, body)


@router.post("/classify")
async def classify(user_id: CurrentUser, body: TaxClassifyRequest) -> dict[str, Any]:
    return await tax_service.classify_period(user_id, body)


@router.patch("/classifications/{transaction_id}")
async def patch_classification(
    user_id: CurrentUser, transaction_id: str, body: TaxClassificationPatch
) -> dict[str, Any]:
    try:
        return await tax_service.patch_classification(user_id, transaction_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/returns/generate")
async def generate_return(user_id: CurrentUser, body: TaxReturnGenerateRequest) -> dict[str, Any]:
    try:
        return await tax_service.generate_return(user_id, body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/returns")
async def list_returns(user_id: CurrentUser) -> dict[str, Any]:
    return {"items": await tax_service.list_returns(user_id)}


@router.get("/returns/{return_id}")
async def get_return(user_id: CurrentUser, return_id: str) -> dict[str, Any]:
    try:
        return await tax_service.get_return(user_id, return_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/returns/{return_id}/status")
async def update_status(
    user_id: CurrentUser, return_id: str, body: TaxReturnStatusUpdate
) -> dict[str, Any]:
    try:
        return await tax_service.update_return_status(user_id, return_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/returns/{return_id}/export.csv")
async def export_csv(user_id: CurrentUser, return_id: str) -> Response:
    try:
        content = await tax_service.export_return_csv(user_id, return_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return PlainTextResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="whorl-tax-{return_id}.csv"'},
    )


@router.get("/returns/{return_id}/export.json")
async def export_json(user_id: CurrentUser, return_id: str) -> dict[str, Any]:
    try:
        return await tax_service.export_return_json(user_id, return_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
