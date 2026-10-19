"""Statutory constants for Nigeria tax computations under the Nigeria Tax Act, 2025.

Rates and thresholds are encoded for reproducible computation in Whorl AI.
They should be reviewed against current FIRS / NRS guidance when law is amended.
"""

from __future__ import annotations

from typing import Any

FRAMEWORK_NAME = "Nigeria Tax Act, 2025 (No. 7)"
FRAMEWORK_EFFECTIVE = "2026-01-01"
AUTHORITY_PRIMARY = "Federal Inland Revenue Service (FIRS) / Nigeria Revenue Service"
CURRENCY = "NGN"

# VAT — NTA Part on Value Added Tax
VAT_RATE = 0.075  # 7.5%
VAT_FILING_DAY = 21  # remittance / return due by 21st of following month (prevailing practice)

# Companies Income Tax — company size & rate (NTA / PwC / KPMG guidance 2026)
CIT_RATE_LARGE = 0.30
CIT_RATE_SMALL = 0.0
SMALL_COMPANY_TURNOVER_CEILING = 100_000_000.0  # ₦100m
SMALL_COMPANY_FIXED_ASSETS_CEILING = 250_000_000.0  # ₦250m

# Development Levy — 4% of assessable profits (replaces TET, NITDA, NASENI, PTF for corporates)
DEVELOPMENT_LEVY_RATE = 0.04

# Capital Gains (corporate) — harmonised toward CIT rate under reforms
CGT_RATE_COMPANY = 0.30

# Electronic Money Transfer Levy / stamp-type bank levies (observed on NG bank rails)
EMTL_TYPICAL_FLAT = 50.0  # illustrative; actual EMTL rules vary by transfer band

# WHT rates: (corporate_resident, corporate_non_resident, non_corp_resident, non_corp_non_resident)
WHT_RATES: dict[str, tuple[float, float, float, float]] = {
    "DIVIDENDS": (0.10, 0.10, 0.10, 0.10),
    "INTEREST": (0.10, 0.10, 0.10, 0.10),
    "ROYALTY": (0.10, 0.10, 0.05, 0.05),
    "RENT": (0.10, 0.10, 0.10, 0.10),
    "PROFESSIONAL": (0.05, 0.10, 0.05, 0.10),  # commission, consultancy, technical, management
    "GOODS_SUPPLY": (0.02, 0.0, 0.02, 0.0),  # non-manufacturer supply
    "SERVICES": (0.02, 0.05, 0.02, 0.05),
    "CONSTRUCTION_MAJOR": (0.02, 0.05, 0.02, 0.05),  # roads, bridges, buildings, power
    "CONSTRUCTION_OTHER": (0.05, 0.10, 0.05, 0.10),
    "BROKERAGE": (0.05, 0.10, 0.05, 0.10),
    "DIRECTORS_FEES": (0.0, 0.0, 0.15, 0.20),
    "NONE": (0.0, 0.0, 0.0, 0.0),
}

WHT_CATEGORY_LABELS: dict[str, str] = {
    "DIVIDENDS": "Dividends",
    "INTEREST": "Interest",
    "ROYALTY": "Royalty",
    "RENT": "Rent, hire or lease",
    "PROFESSIONAL": "Commission, consultancy, technical, management & professional fees",
    "GOODS_SUPPLY": "Supply of goods/materials (other than by manufacturer)",
    "SERVICES": "Supply/rendering of other services",
    "CONSTRUCTION_MAJOR": "Construction — roads, bridges, buildings, power plants",
    "CONSTRUCTION_OTHER": "Other construction and related activities",
    "BROKERAGE": "Brokerage fee",
    "DIRECTORS_FEES": "Directors' fees",
    "NONE": "Not subject to WHT",
}

COUNTERPARTY_INDEX = {
    "CORPORATE_RESIDENT": 0,
    "CORPORATE_NON_RESIDENT": 1,
    "NON_CORPORATE_RESIDENT": 2,
    "NON_CORPORATE_NON_RESIDENT": 3,
}

VAT_EXEMPT_HINTS = (
    "shared passenger",
    "road transport",
    "petroleum",
    "crude",
    "cng",
    "lpg",
    "renewable energy",
    "land ",
    "building",
    "government licence",
    "diploma",
    "wheelchair",
    "sanitary",
    "baby product",
)

BANK_VAT_HINTS = (
    "vat on nip",
    "vat on transfer",
    "vat on sms",
    "vat on charge",
    "vat/",
    " vat ",
)

STAMP_OR_LEVY_HINTS = (
    "stamp duty",
    "stampduty",
    "electronic money transfer levy",
    "emtl",
    "nip charge",
    "sms alert charge",
)

TRANSFER_HINTS = (
    "transfer to",
    "transfer from",
    "trf/",
    "nip/",
    "inward transfer",
    "outward transfer",
    "own account",
)

INTEREST_HINTS = ("interest", "credit interest", "savings interest")
RENT_HINTS = ("rent", "lease", "hire of")
PROFESSIONAL_HINTS = (
    "consult",
    "advisory",
    "legal fee",
    "audit fee",
    "professional",
    "management fee",
    "retainer",
    "agency fee",
)
CONSTRUCTION_HINTS = ("construction", "contractor", "civil works", "building project")
GOODS_HINTS = ("goods", "inventory", "supplies", "materials", "procurement")
SALARY_HINTS = ("salary", "payroll", "wages", "paye", "staff payment")


def wht_rate_for(category: str, counterparty: str) -> float:
    rates = WHT_RATES.get(category.upper(), WHT_RATES["NONE"])
    idx = COUNTERPARTY_INDEX.get(counterparty, 0)
    return float(rates[idx])


def company_size_band(turnover: float, fixed_assets: float) -> str:
    if turnover <= SMALL_COMPANY_TURNOVER_CEILING and fixed_assets <= SMALL_COMPANY_FIXED_ASSETS_CEILING:
        return "SMALL"
    return "LARGE"


def cit_rate_for_band(band: str) -> float:
    return CIT_RATE_SMALL if band == "SMALL" else CIT_RATE_LARGE


def statutory_reference_pack() -> dict[str, Any]:
    return {
        "framework": FRAMEWORK_NAME,
        "effective_from": FRAMEWORK_EFFECTIVE,
        "authority": AUTHORITY_PRIMARY,
        "vat_rate": VAT_RATE,
        "cit_rate_large": CIT_RATE_LARGE,
        "cit_rate_small": CIT_RATE_SMALL,
        "small_company_turnover_ceiling": SMALL_COMPANY_TURNOVER_CEILING,
        "small_company_fixed_assets_ceiling": SMALL_COMPANY_FIXED_ASSETS_CEILING,
        "development_levy_rate": DEVELOPMENT_LEVY_RATE,
        "cgt_rate_company": CGT_RATE_COMPANY,
        "vat_filing_day": VAT_FILING_DAY,
        "notes": [
            "VAT charged at 7.5% on taxable supplies except where exempt under the NTA.",
            "Small companies (turnover ≤ ₦100m and fixed assets ≤ ₦250m) are generally at 0% CIT and exempt from Development Levy.",
            "Development Levy is 4% of assessable profits for chargeable resident companies (non-small).",
            "WHT rates follow the published transaction schedule for resident/non-resident counterparties.",
            "Bank-feed based computations are cash-movement informed; accrual adjustments should be applied from books where available.",
        ],
    }
