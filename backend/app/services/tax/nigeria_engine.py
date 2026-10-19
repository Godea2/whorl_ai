"""Build FIRS-ready statutory schedules from classified Nigerian transactions."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from app.services.tax.nigeria_constants import (
    DEVELOPMENT_LEVY_RATE,
    FRAMEWORK_NAME,
    VAT_FILING_DAY,
    VAT_RATE,
    WHT_CATEGORY_LABELS,
    cit_rate_for_band,
    company_size_band,
    statutory_reference_pack,
)


def _money(v: float) -> float:
    return round(float(v or 0), 2)


def period_label(start: date, end: date) -> str:
    if start.day == 1 and end.day == monthrange(end.year, end.month)[1] and start.month == end.month:
        return start.strftime("%B %Y")
    return f"{start.isoformat()} to {end.isoformat()}"


def filing_due_date(period_end: date, day: int = VAT_FILING_DAY) -> date:
    y, m = period_end.year, period_end.month
    if m == 12:
        return date(y + 1, 1, min(day, 28))
    nm = m + 1
    last = monthrange(y, nm)[1]
    return date(y, nm, min(day, last))


def build_line(
    txn: dict[str, Any],
    cls: dict[str, Any],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "transaction_id": txn.get("id"),
        "date": txn.get("transaction_date"),
        "description": txn.get("description") or txn.get("merchant_name") or "—",
        "merchant": txn.get("merchant_name") or "—",
        "category": txn.get("category") or "Uncategorized",
        "type": txn.get("transaction_type"),
        "currency": txn.get("currency") or "NGN",
        "gross_amount": _money(cls.get("gross_amount")),
        "net_amount": _money(cls.get("net_amount")),
        "vat_treatment": cls.get("vat_treatment"),
        "vat_amount": _money(cls.get("vat_amount")),
        "wht_category": cls.get("wht_category"),
        "wht_amount": _money(cls.get("wht_amount")),
        "wht_role": cls.get("wht_role"),
        "cit_treatment": cls.get("cit_treatment"),
        "levy_flags": cls.get("levy_flags") or [],
        "confidence": cls.get("confidence"),
        "rationale": cls.get("rationale"),
        "account_id": txn.get("account_id"),
    }
    if extra:
        row.update(extra)
    return row


def compute_schedules(
    *,
    profile: dict[str, Any],
    period_start: date,
    period_end: date,
    classified_rows: list[tuple[dict[str, Any], dict[str, Any]]],
    books_pnl: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return cover + schedules + liabilities suitable for professional presentation."""

    output_vat_lines: list[dict[str, Any]] = []
    input_vat_lines: list[dict[str, Any]] = []
    bank_vat_lines: list[dict[str, Any]] = []
    exempt_lines: list[dict[str, Any]] = []
    wht_agent_lines: list[dict[str, Any]] = []
    wht_suffered_lines: list[dict[str, Any]] = []
    cit_income_lines: list[dict[str, Any]] = []
    cit_deductible_lines: list[dict[str, Any]] = []
    cit_non_deductible_lines: list[dict[str, Any]] = []
    levy_lines: list[dict[str, Any]] = []
    paye_lines: list[dict[str, Any]] = []
    transfer_lines: list[dict[str, Any]] = []

    cash_in = 0.0
    cash_out = 0.0

    for txn, cls in classified_rows:
        line = build_line(txn, cls)
        amt = _money(txn.get("amount"))
        if str(txn.get("transaction_type")).lower() == "credit":
            cash_in += amt
        else:
            cash_out += amt

        vat_t = cls.get("vat_treatment")
        if vat_t == "STANDARD_OUTPUT":
            output_vat_lines.append(line)
        elif vat_t in {"STANDARD_INPUT", "NON_DEDUCTIBLE_INPUT"}:
            input_vat_lines.append(line)
        elif vat_t == "BANK_CHARGE_VAT":
            bank_vat_lines.append(line)
        elif vat_t in {"EXEMPT", "ZERO_RATED"}:
            exempt_lines.append(line)

        if cls.get("wht_role") == "AGENT_DEDUCTED" and _money(cls.get("wht_amount")) > 0:
            wht_agent_lines.append(line)
        if cls.get("wht_role") == "SUFFERED" and _money(cls.get("wht_amount")) > 0:
            wht_suffered_lines.append(line)

        cit_t = cls.get("cit_treatment")
        if cit_t == "TAXABLE_INCOME":
            cit_income_lines.append(line)
        elif cit_t == "DEDUCTIBLE_EXPENSE":
            cit_deductible_lines.append(line)
        elif cit_t == "NON_DEDUCTIBLE":
            cit_non_deductible_lines.append(line)
        elif cit_t == "TRANSFER":
            transfer_lines.append(line)

        flags = cls.get("levy_flags") or []
        if flags:
            levy_lines.append(line)
        if "PAYE_CANDIDATE" in flags:
            paye_lines.append(line)

    output_vat = _money(sum(x["vat_amount"] for x in output_vat_lines))
    input_vat = _money(sum(x["vat_amount"] for x in input_vat_lines))
    bank_vat = _money(sum(x["vat_amount"] for x in bank_vat_lines))
    # Bank charge VAT is generally not creditable input VAT for most taxpayers
    creditable_input = input_vat
    net_vat_payable = _money(output_vat - creditable_input)

    wht_agent_total = _money(sum(x["wht_amount"] for x in wht_agent_lines))
    wht_suffered_total = _money(sum(x["wht_amount"] for x in wht_suffered_lines))

    # CIT — cash-informed baseline
    taxable_income_cash = _money(sum(x["net_amount"] or x["gross_amount"] for x in cit_income_lines))
    deductible_cash = _money(sum(x["net_amount"] or x["gross_amount"] for x in cit_deductible_lines))
    non_deductible_cash = _money(sum(x["gross_amount"] for x in cit_non_deductible_lines))

    books_revenue = None
    books_expenses = None
    books_net = None
    if books_pnl:
        books_revenue = _money(books_pnl.get("total_income") or books_pnl.get("revenue") or 0)
        books_expenses = _money(books_pnl.get("total_expenses") or books_pnl.get("expenses") or 0)
        books_net = _money(books_pnl.get("net_profit") or (books_revenue - books_expenses))

    # Prefer books for assessable profit when available; else cash net of transfers
    assessable_profit_cash = _money(taxable_income_cash - deductible_cash)
    assessable_profit = books_net if books_net is not None else assessable_profit_cash
    if assessable_profit < 0:
        assessable_profit_for_levy = 0.0
    else:
        assessable_profit_for_levy = assessable_profit

    turnover_proxy = books_revenue if books_revenue is not None else taxable_income_cash
    fixed_assets = _money(profile.get("fixed_assets_ngn") or 0)
    size_band = company_size_band(turnover_proxy, fixed_assets)
    cit_rate = cit_rate_for_band(size_band)
    cit_payable = _money(max(assessable_profit, 0) * cit_rate)

    development_levy = 0.0
    if size_band != "SMALL" and str(profile.get("entity_type") or "COMPANY") == "COMPANY":
        development_levy = _money(assessable_profit_for_levy * DEVELOPMENT_LEVY_RATE)

    stamp_total = _money(
        sum(x["gross_amount"] for x in levy_lines if "STAMP_DUTY" in (x.get("levy_flags") or []))
    )
    emtl_total = _money(
        sum(x["gross_amount"] for x in levy_lines if "EMTL" in (x.get("levy_flags") or []))
    )
    paye_gross = _money(sum(x["gross_amount"] for x in paye_lines))

    due = filing_due_date(period_end)
    label = period_label(period_start, period_end)

    # WHT by category summary
    wht_by_cat: dict[str, dict[str, Any]] = {}
    for line in wht_agent_lines:
        cat = line.get("wht_category") or "NONE"
        bucket = wht_by_cat.setdefault(
            cat,
            {
                "category": cat,
                "label": WHT_CATEGORY_LABELS.get(cat, cat),
                "count": 0,
                "taxable_base": 0.0,
                "wht_amount": 0.0,
            },
        )
        bucket["count"] += 1
        bucket["taxable_base"] = _money(bucket["taxable_base"] + (line.get("net_amount") or line["gross_amount"]))
        bucket["wht_amount"] = _money(bucket["wht_amount"] + line["wht_amount"])

    schedules = [
        {
            "schedule_code": "COVER",
            "schedule_title": "Cover Sheet — Statutory Tax Report Pack",
            "sort_order": 0,
            "totals_json": {
                "period_label": label,
                "framework": FRAMEWORK_NAME,
                "filing_due_date": due.isoformat(),
                "net_vat_payable": net_vat_payable,
                "wht_remittable": wht_agent_total,
                "cit_payable": cit_payable,
                "development_levy": development_levy,
                "total_statutory_outflow": _money(
                    max(net_vat_payable, 0) + wht_agent_total + cit_payable + development_levy
                ),
            },
            "lines_json": [],
            "notes": "Prepared for presentation to tax authorities and professional advisers.",
        },
        {
            "schedule_code": "VAT_01",
            "schedule_title": "Schedule VAT-01 — Value Added Tax Account (7.5%)",
            "sort_order": 10,
            "totals_json": {
                "output_vat": output_vat,
                "input_vat_creditable": creditable_input,
                "bank_charge_vat_non_creditable": bank_vat,
                "net_vat_payable_or_refundable": net_vat_payable,
                "standard_rate": VAT_RATE,
                "output_line_count": len(output_vat_lines),
                "input_line_count": len(input_vat_lines),
            },
            "lines_json": {
                "output": output_vat_lines,
                "input": input_vat_lines,
                "bank_vat": bank_vat_lines,
                "exempt_or_zero": exempt_lines,
            },
            "notes": (
                "Output VAT extracted from VAT-inclusive receipts where classified STANDARD_OUTPUT. "
                "Input VAT claimed only on STANDARD_INPUT lines. Bank-charge VAT is disclosed separately "
                "and excluded from creditable input pending invoice-level confirmation."
            ),
        },
        {
            "schedule_code": "WHT_01",
            "schedule_title": "Schedule WHT-01 — Withholding Tax Deducted (as Agent)",
            "sort_order": 20,
            "totals_json": {
                "total_wht_deducted": wht_agent_total,
                "by_category": list(wht_by_cat.values()),
                "line_count": len(wht_agent_lines),
                "remittance_due_date": due.isoformat(),
            },
            "lines_json": wht_agent_lines,
            "notes": (
                "WHT computed on classified contract categories using resident/non-resident rate matrix. "
                "Remit to FIRS with schedule of beneficiaries; due by the 21st of the following month."
            ),
        },
        {
            "schedule_code": "WHT_02",
            "schedule_title": "Schedule WHT-02 — Withholding Tax Suffered (Credits)",
            "sort_order": 30,
            "totals_json": {
                "total_wht_suffered": wht_suffered_total,
                "line_count": len(wht_suffered_lines),
            },
            "lines_json": wht_suffered_lines,
            "notes": "Available as credit against CIT / as evidence of tax already deducted at source.",
        },
        {
            "schedule_code": "CIT_01",
            "schedule_title": "Schedule CIT-01 — Companies Income Tax Computation",
            "sort_order": 40,
            "totals_json": {
                "size_band": size_band,
                "cit_rate": cit_rate,
                "turnover_proxy": _money(turnover_proxy),
                "fixed_assets_ngn": fixed_assets,
                "taxable_income_cash": taxable_income_cash,
                "deductible_expenses_cash": deductible_cash,
                "non_deductible_expenses": non_deductible_cash,
                "assessable_profit_cash_basis": assessable_profit_cash,
                "books_revenue": books_revenue,
                "books_expenses": books_expenses,
                "books_net_profit": books_net,
                "assessable_profit_adopted": _money(assessable_profit),
                "cit_payable": cit_payable,
                "basis": "books_pnl" if books_net is not None else "classified_cash_movements",
            },
            "lines_json": {
                "income": cit_income_lines,
                "deductible": cit_deductible_lines,
                "non_deductible": cit_non_deductible_lines,
            },
            "notes": (
                "Small company test: turnover ≤ ₦100,000,000 and fixed assets ≤ ₦250,000,000 → 0% CIT. "
                "Large companies → 30%. Adopted profit prefers QuickBooks P&L when connected; otherwise "
                "classified cash basis. Capital allowances and loss b/f require books adjustments."
            ),
        },
        {
            "schedule_code": "DEV_01",
            "schedule_title": "Schedule DEV-01 — Development Levy (4% of Assessable Profits)",
            "sort_order": 50,
            "totals_json": {
                "rate": DEVELOPMENT_LEVY_RATE,
                "assessable_profit": _money(assessable_profit_for_levy),
                "development_levy_payable": development_levy,
                "applicable": size_band != "SMALL",
            },
            "lines_json": [],
            "notes": (
                "Development Levy consolidates prior TET / NITDA / NASENI / Police Trust Fund style levies. "
                "Not applicable to small companies or non-resident companies."
            ),
        },
        {
            "schedule_code": "LEVY_01",
            "schedule_title": "Schedule LEVY-01 — Stamp Duty, EMTL & Bank Levies",
            "sort_order": 60,
            "totals_json": {
                "stamp_duty": stamp_total,
                "emtl": emtl_total,
                "other_bank_charges_vat": bank_vat,
                "line_count": len(levy_lines),
            },
            "lines_json": levy_lines,
            "notes": "Observed statutory and quasi-statutory deductions on Nigerian payment rails.",
        },
        {
            "schedule_code": "PAYE_01",
            "schedule_title": "Schedule PAYE-01 — Payroll Candidates (State IRS)",
            "sort_order": 70,
            "totals_json": {
                "gross_payroll_candidates": paye_gross,
                "line_count": len(paye_lines),
            },
            "lines_json": paye_lines,
            "notes": (
                "PAYE is administered by State Internal Revenue Services. This schedule flags salary-like "
                "outflows for remittance pack preparation; exact PAYE requires payroll engine & tax clubs."
            ),
        },
        {
            "schedule_code": "XFER_01",
            "schedule_title": "Schedule XFER-01 — Transfers Excluded from Taxable Supplies",
            "sort_order": 80,
            "totals_json": {
                "transfer_count": len(transfer_lines),
                "transfer_volume": _money(sum(x["gross_amount"] for x in transfer_lines)),
            },
            "lines_json": transfer_lines,
            "notes": "Excluded from VAT supplies and CIT profit to avoid double-counting internal movements.",
        },
        {
            "schedule_code": "CASH_01",
            "schedule_title": "Schedule CASH-01 — Period Cash Movement Bridge",
            "sort_order": 90,
            "totals_json": {
                "cash_inflows": _money(cash_in),
                "cash_outflows": _money(cash_out),
                "net_cash": _money(cash_in - cash_out),
                "transaction_count": len(classified_rows),
            },
            "lines_json": [],
            "notes": "Bridge from bank activity to tax schedules for audit trail.",
        },
    ]

    liabilities = {
        "vat_payable": max(net_vat_payable, 0),
        "vat_refundable": abs(min(net_vat_payable, 0)),
        "wht_remittable": wht_agent_total,
        "wht_credit": wht_suffered_total,
        "cit_payable": cit_payable,
        "development_levy_payable": development_levy,
        "stamp_duty_observed": stamp_total,
        "emtl_observed": emtl_total,
        "total_due_to_firs_estimate": _money(
            max(net_vat_payable, 0) + wht_agent_total + cit_payable + development_levy
        ),
        "filing_due_date": due.isoformat(),
    }

    cover = {
        "document_title": "Nigeria Statutory Tax Report Pack",
        "subtitle": "VAT • WHT • Companies Income Tax • Development Levy",
        "framework": FRAMEWORK_NAME,
        "authority": "Prepared for filing / review with the Federal Inland Revenue Service (FIRS)",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_label": label,
        "generated_for": {
            "legal_name": profile.get("legal_name"),
            "trading_name": profile.get("trading_name"),
            "tin": profile.get("tin"),
            "rc_number": profile.get("rc_number"),
            "tax_office": profile.get("tax_office"),
            "business_address": profile.get("business_address"),
            "state_of_operation": profile.get("state_of_operation"),
            "entity_type": profile.get("entity_type"),
            "vat_registered": profile.get("vat_registered"),
        },
        "company_size_band": size_band,
        "currency": profile.get("currency") or "NGN",
        "liabilities": liabilities,
        "attestation": {
            "statement": (
                "I/We certify that this report pack was prepared from the organisation's connected "
                "financial records (bank feeds and, where available, accounting books), classified under "
                f"{FRAMEWORK_NAME}. Figures are presented for statutory review and remittance. "
                "The taxpayer remains responsible for final returns lodged with FIRS and relevant State IRS."
            ),
            "sign_off_roles": [
                "Prepared by — Finance / Tax Manager",
                "Reviewed by — External Tax Adviser (recommended)",
                "Approved by — Director / Managing Partner",
            ],
        },
        "methodology": [
            "Transactions classified automatically using Nigerian bank narration patterns, categories, and statutory rate tables; manual overrides stored per transaction.",
            "VAT assumes standard-rated supplies are VAT-inclusive unless classified as exempt/out-of-scope.",
            "WHT uses the published category matrix for the entity's default counterparty residency profile.",
            "CIT adopts QuickBooks P&L net profit when available; otherwise classified cash taxable income less deductible expenses.",
            "Development Levy at 4% of assessable profits for non-small resident companies.",
            "This pack is designed for professional presentation; capital allowances, loss relief, and invoice-level VAT evidence should be attached from books where applicable.",
        ],
        "statutory_references": statutory_reference_pack(),
    }

    return {
        "cover": cover,
        "schedules": schedules,
        "liabilities": liabilities,
        "summary": {
            "period_label": label,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "size_band": size_band,
            "cit_rate": cit_rate,
            "output_vat": output_vat,
            "input_vat": creditable_input,
            "net_vat": net_vat_payable,
            "wht_agent": wht_agent_total,
            "wht_suffered": wht_suffered_total,
            "cit_payable": cit_payable,
            "development_levy": development_levy,
            "total_firs_estimate": liabilities["total_due_to_firs_estimate"],
            "filing_due_date": due.isoformat(),
            "classified_count": len(classified_rows),
        },
    }
