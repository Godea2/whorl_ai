from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaxProfileUpsert(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)
    trading_name: str | None = None
    tin: str | None = None
    rc_number: str | None = None
    tax_office: str | None = None
    business_address: str | None = None
    state_of_operation: str | None = None
    sector: str | None = None
    entity_type: Literal["COMPANY", "ENTERPRISE", "PARTNERSHIP", "INDIVIDUAL"] = "COMPANY"
    accounting_year_end_month: int = Field(default=12, ge=1, le=12)
    currency: str = "NGN"
    fixed_assets_ngn: float = 0
    vat_registered: bool = True
    vat_filing_frequency: Literal["MONTHLY", "QUARTERLY"] = "MONTHLY"
    default_wht_counterparty_type: Literal[
        "CORPORATE_RESIDENT",
        "CORPORATE_NON_RESIDENT",
        "NON_CORPORATE_RESIDENT",
        "NON_CORPORATE_NON_RESIDENT",
    ] = "CORPORATE_RESIDENT"
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None


class TaxClassifyRequest(BaseModel):
    date_from: date
    date_to: date
    account_ids: list[str] | None = None
    persist: bool = True
    reclassify_manual: bool = False


class TaxClassificationPatch(BaseModel):
    vat_treatment: str | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None
    net_amount: float | None = None
    gross_amount: float | None = None
    wht_category: str | None = None
    wht_rate: float | None = None
    wht_amount: float | None = None
    wht_role: str | None = None
    cit_treatment: str | None = None
    levy_flags: list[str] | None = None
    rationale: str | None = None


class TaxReturnGenerateRequest(BaseModel):
    period_start: date
    period_end: date
    account_ids: list[str] | None = None
    include_books_pnl: bool = True
    persist_classifications: bool = True
    return_type: Literal[
        "COMBINED_STATUTORY", "VAT", "WHT", "CIT", "DEVELOPMENT_LEVY", "CUSTOM"
    ] = "COMBINED_STATUTORY"


class TaxReturnStatusUpdate(BaseModel):
    status: Literal["DRAFT", "IN_REVIEW", "FINALIZED"]
