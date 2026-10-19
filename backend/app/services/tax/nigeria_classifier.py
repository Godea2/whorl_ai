"""Classify bank / books transactions for Nigeria VAT, WHT, CIT and levies."""

from __future__ import annotations

from typing import Any

from app.services.tax.nigeria_constants import (
    BANK_VAT_HINTS,
    CONSTRUCTION_HINTS,
    GOODS_HINTS,
    INTEREST_HINTS,
    PROFESSIONAL_HINTS,
    RENT_HINTS,
    SALARY_HINTS,
    STAMP_OR_LEVY_HINTS,
    TRANSFER_HINTS,
    VAT_EXEMPT_HINTS,
    VAT_RATE,
    wht_rate_for,
)


def _text(txn: dict[str, Any]) -> str:
    parts = [
        txn.get("description") or "",
        txn.get("merchant_name") or "",
        txn.get("category") or "",
        txn.get("sub_category") or "",
    ]
    meta = txn.get("raw_metadata") or {}
    if isinstance(meta, dict):
        parts.append(str(meta.get("narration") or ""))
        parts.append(str(meta.get("type") or ""))
    return " ".join(parts).lower()


def _amount(txn: dict[str, Any]) -> float:
    try:
        return abs(float(txn.get("amount") or 0))
    except (TypeError, ValueError):
        return 0.0


def _is_debit(txn: dict[str, Any]) -> bool:
    return str(txn.get("transaction_type") or "").lower() in {"debit", "outflow", "expense"}


def _split_vat_inclusive(gross: float, rate: float = VAT_RATE) -> tuple[float, float]:
    if gross <= 0 or rate <= 0:
        return gross, 0.0
    net = round(gross / (1 + rate), 2)
    vat = round(gross - net, 2)
    return net, vat


def classify_transaction(
    txn: dict[str, Any],
    *,
    counterparty: str = "CORPORATE_RESIDENT",
    source: str = "AUTO",
) -> dict[str, Any]:
    """Return a tax_transaction_classifications-shaped dict (without ids)."""
    text = _text(txn)
    gross = _amount(txn)
    debit = _is_debit(txn)
    category = str(txn.get("category") or "").lower()

    vat_treatment = "OUT_OF_SCOPE"
    vat_rate = 0.0
    vat_amount = 0.0
    net_amount = gross
    wht_category = "NONE"
    wht_role = "NONE"
    wht_rate = 0.0
    wht_amount = 0.0
    cit_treatment = "NEUTRAL"
    levy_flags: list[str] = []
    confidence = 0.55
    rationale_parts: list[str] = []

    # Explicit bank VAT lines (common on Nigerian rails)
    if any(h in text for h in BANK_VAT_HINTS):
        vat_treatment = "BANK_CHARGE_VAT"
        vat_rate = VAT_RATE
        vat_amount = gross
        net_amount = 0.0
        cit_treatment = "DEDUCTIBLE_EXPENSE" if debit else "NEUTRAL"
        confidence = 0.95
        rationale_parts.append("Narration indicates bank-charge VAT (e.g. VAT on NIP/SMS).")

    elif any(h in text for h in STAMP_OR_LEVY_HINTS):
        vat_treatment = "OUT_OF_SCOPE"
        cit_treatment = "DEDUCTIBLE_EXPENSE" if debit else "NEUTRAL"
        if "stamp" in text:
            levy_flags.append("STAMP_DUTY")
        if "emtl" in text or "electronic money transfer levy" in text:
            levy_flags.append("EMTL")
        if "nip charge" in text or "sms alert" in text:
            levy_flags.append("BANK_CHARGE")
        confidence = 0.9
        rationale_parts.append("Identified as stamp duty / EMTL / bank charge levy.")

    elif any(h in text for h in TRANSFER_HINTS) or "transfer" in category:
        vat_treatment = "OUT_OF_SCOPE"
        cit_treatment = "TRANSFER"
        confidence = 0.75
        rationale_parts.append("Treated as inter-account / customer transfer (outside VAT supply).")

    elif any(h in text for h in SALARY_HINTS) or category in {"payroll", "salary"}:
        vat_treatment = "OUT_OF_SCOPE"
        cit_treatment = "DEDUCTIBLE_EXPENSE" if debit else "NEUTRAL"
        levy_flags.append("PAYE_CANDIDATE")
        confidence = 0.8
        rationale_parts.append("Payroll-like payment — PAYE/state PAYE schedule candidate; outside VAT.")

    elif any(h in text for h in VAT_EXEMPT_HINTS):
        vat_treatment = "EXEMPT"
        vat_rate = 0.0
        cit_treatment = "DEDUCTIBLE_EXPENSE" if debit else "TAXABLE_INCOME"
        confidence = 0.7
        rationale_parts.append("Narration/category aligns with NTA VAT-exempt themes.")

    elif debit:
        # Purchases / expenses — potential input VAT if standard-rated
        if any(h in text for h in PROFESSIONAL_HINTS) or category in {"software", "professional", "services"}:
            vat_treatment = "STANDARD_INPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            wht_category = "PROFESSIONAL"
            wht_role = "AGENT_DEDUCTED"
            cit_treatment = "DEDUCTIBLE_EXPENSE"
            confidence = 0.72
            rationale_parts.append("Professional/service spend — input VAT (gross-up) + WHT agent candidate.")
        elif any(h in text for h in RENT_HINTS):
            vat_treatment = "EXEMPT"  # land/building interest often exempt; rent of commercial services may differ
            wht_category = "RENT"
            wht_role = "AGENT_DEDUCTED"
            cit_treatment = "DEDUCTIBLE_EXPENSE"
            confidence = 0.7
            rationale_parts.append("Rent/hire/lease — WHT on rent; VAT often exempt for land/building interests.")
        elif any(h in text for h in CONSTRUCTION_HINTS):
            vat_treatment = "STANDARD_INPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            wht_category = "CONSTRUCTION_OTHER"
            wht_role = "AGENT_DEDUCTED"
            cit_treatment = "DEDUCTIBLE_EXPENSE"
            confidence = 0.68
            rationale_parts.append("Construction-related outflow — input VAT + construction WHT schedule.")
        elif any(h in text for h in GOODS_HINTS) or category in {"shopping", "inventory", "cost of sales"}:
            vat_treatment = "STANDARD_INPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            wht_category = "GOODS_SUPPLY"
            wht_role = "AGENT_DEDUCTED"
            cit_treatment = "DEDUCTIBLE_EXPENSE"
            confidence = 0.65
            rationale_parts.append("Goods/materials purchase — assumed VAT-inclusive; WHT on non-manufacturer supply.")
        elif category in {"utilities", "transport", "meals", "entertainment", "office", "fees"}:
            vat_treatment = "STANDARD_INPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            wht_category = "SERVICES" if category in {"fees", "utilities"} else "NONE"
            wht_role = "AGENT_DEDUCTED" if wht_category != "NONE" else "NONE"
            cit_treatment = "DEDUCTIBLE_EXPENSE"
            if category == "entertainment":
                cit_treatment = "NON_DEDUCTIBLE"
                rationale_parts.append("Entertainment often restricted for CIT — flagged non-deductible pending policy.")
            else:
                rationale_parts.append("Operating expense — standard-rated input VAT assumed on cash gross.")
            confidence = 0.6
        else:
            vat_treatment = "STANDARD_INPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            cit_treatment = "DEDUCTIBLE_EXPENSE"
            confidence = 0.5
            rationale_parts.append("Default debit treatment: VAT-inclusive deductible expense (review recommended).")
    else:
        # Credits / inflows
        if any(h in text for h in INTEREST_HINTS) or category == "interest":
            vat_treatment = "EXEMPT"
            wht_category = "INTEREST"
            wht_role = "SUFFERED"
            cit_treatment = "TAXABLE_INCOME"
            confidence = 0.8
            rationale_parts.append("Interest income — CIT taxable; WHT on interest may have been suffered upstream.")
        elif any(h in text for h in PROFESSIONAL_HINTS) or category in {"services", "sales", "income"}:
            vat_treatment = "STANDARD_OUTPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            cit_treatment = "TAXABLE_INCOME"
            confidence = 0.7
            rationale_parts.append("Revenue-like credit — output VAT extracted from VAT-inclusive receipt.")
        else:
            vat_treatment = "STANDARD_OUTPUT"
            vat_rate = VAT_RATE
            net_amount, vat_amount = _split_vat_inclusive(gross, VAT_RATE)
            cit_treatment = "TAXABLE_INCOME"
            confidence = 0.55
            rationale_parts.append("Default credit treatment: VAT-inclusive taxable income (review recommended).")

    if wht_category != "NONE":
        wht_rate = wht_rate_for(wht_category, counterparty)
        # WHT is computed on the net-of-VAT / contract sum conventionally
        base = net_amount if net_amount > 0 else gross
        wht_amount = round(base * wht_rate, 2)

    return {
        "vat_treatment": vat_treatment,
        "vat_rate": vat_rate,
        "vat_amount": round(vat_amount, 2),
        "net_amount": round(net_amount, 2),
        "gross_amount": round(gross, 2),
        "wht_category": wht_category,
        "wht_rate": wht_rate,
        "wht_amount": round(wht_amount, 2),
        "wht_role": wht_role,
        "cit_treatment": cit_treatment,
        "levy_flags": levy_flags,
        "confidence": confidence,
        "source": source,
        "rationale": " ".join(rationale_parts),
    }
