"""Orchestration for Nigeria tax profiles, classification, and statutory report packs."""

from __future__ import annotations

import csv
import io
import json
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any

from app.database import get_supabase, run_db
from app.models.tax import (
    TaxClassificationPatch,
    TaxClassifyRequest,
    TaxProfileUpsert,
    TaxReturnGenerateRequest,
)
from app.services.tax.nigeria_classifier import classify_transaction
from app.services.tax.nigeria_constants import FRAMEWORK_NAME, statutory_reference_pack
from app.services.tax.nigeria_engine import compute_schedules, period_label


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(res: Any) -> list[dict[str, Any]]:
    data = getattr(res, "data", None)
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


async def get_or_create_profile(user_id: str) -> dict[str, Any]:
    sb = get_supabase()
    existing = await run_db(
        lambda: sb.table("tax_profiles").select("*").eq("user_id", user_id).limit(1).execute()
    )
    rows = _rows(existing)
    if rows:
        return rows[0]

    user_res = await run_db(
        lambda: sb.table("users").select("email, full_name, country, currency").eq("id", user_id).limit(1).execute()
    )
    user = (_rows(user_res) or [{}])[0]
    legal = user.get("full_name") or (user.get("email") or "Taxpayer").split("@")[0]
    payload = {
        "user_id": user_id,
        "legal_name": legal,
        "trading_name": legal,
        "currency": "NGN" if (user.get("country") or "").upper() in {"NG", "NGA", "NIGERIA", ""} else (user.get("currency") or "NGN"),
        "state_of_operation": None,
        "entity_type": "COMPANY",
        "vat_registered": True,
        "updated_at": _utcnow(),
    }
    created = await run_db(lambda: sb.table("tax_profiles").upsert(payload, on_conflict="user_id").execute())
    return (_rows(created) or [payload])[0]


async def upsert_profile(user_id: str, body: TaxProfileUpsert) -> dict[str, Any]:
    sb = get_supabase()
    payload = body.model_dump()
    payload["user_id"] = user_id
    payload["updated_at"] = _utcnow()
    res = await run_db(lambda: sb.table("tax_profiles").upsert(payload, on_conflict="user_id").execute())
    rows = _rows(res)
    return rows[0] if rows else payload


async def _fetch_transactions(
    user_id: str,
    date_from: date,
    date_to: date,
    account_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    sb = get_supabase()
    query = (
        sb.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .gte("transaction_date", date_from.isoformat())
        .lte("transaction_date", date_to.isoformat())
        .order("transaction_date")
    )
    if account_ids:
        query = query.in_("account_id", account_ids)
    res = await run_db(lambda: query.execute())
    return _rows(res)


async def _existing_classifications(user_id: str, txn_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not txn_ids:
        return {}
    sb = get_supabase()
    out: dict[str, dict[str, Any]] = {}
    chunk = 200
    for i in range(0, len(txn_ids), chunk):
        part = txn_ids[i : i + chunk]
        res = await run_db(
            lambda p=part: sb.table("tax_transaction_classifications")
            .select("*")
            .eq("user_id", user_id)
            .in_("transaction_id", p)
            .execute()
        )
        for row in _rows(res):
            out[row["transaction_id"]] = row
    return out


async def classify_period(user_id: str, req: TaxClassifyRequest) -> dict[str, Any]:
    profile = await get_or_create_profile(user_id)
    counterparty = profile.get("default_wht_counterparty_type") or "CORPORATE_RESIDENT"
    txns = await _fetch_transactions(user_id, req.date_from, req.date_to, req.account_ids)
    existing = await _existing_classifications(user_id, [t["id"] for t in txns if t.get("id")])

    results: list[dict[str, Any]] = []
    to_upsert: list[dict[str, Any]] = []

    for txn in txns:
        tid = txn["id"]
        prev = existing.get(tid)
        if prev and prev.get("source") == "MANUAL" and not req.reclassify_manual:
            cls = prev
        else:
            source = "SYNTHETIC" if txn.get("is_synthetic") else "AUTO"
            auto = classify_transaction(txn, counterparty=counterparty, source=source)
            cls = {**auto, "user_id": user_id, "transaction_id": tid, "updated_at": _utcnow()}
            if req.persist:
                to_upsert.append(cls)
        results.append({"transaction": txn, "classification": cls})

    if req.persist and to_upsert:
        sb = get_supabase()
        for i in range(0, len(to_upsert), 50):
            chunk = to_upsert[i : i + 50]
            await run_db(
                lambda c=chunk: sb.table("tax_transaction_classifications")
                .upsert(c, on_conflict="user_id,transaction_id")
                .execute()
            )

    return {
        "count": len(results),
        "persisted": len(to_upsert) if req.persist else 0,
        "items": [
            {
                "transaction_id": r["transaction"]["id"],
                "date": r["transaction"].get("transaction_date"),
                "description": r["transaction"].get("description"),
                "amount": r["transaction"].get("amount"),
                "type": r["transaction"].get("transaction_type"),
                **{k: r["classification"].get(k) for k in (
                    "vat_treatment", "vat_amount", "net_amount", "gross_amount",
                    "wht_category", "wht_amount", "wht_role", "cit_treatment",
                    "levy_flags", "confidence", "source", "rationale",
                )},
            }
            for r in results
        ],
    }


async def patch_classification(
    user_id: str, transaction_id: str, body: TaxClassificationPatch
) -> dict[str, Any]:
    sb = get_supabase()
    txn_res = await run_db(
        lambda: sb.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", transaction_id)
        .limit(1)
        .execute()
    )
    txns = _rows(txn_res)
    if not txns:
        raise ValueError("Transaction not found")

    profile = await get_or_create_profile(user_id)
    base = classify_transaction(
        txns[0],
        counterparty=profile.get("default_wht_counterparty_type") or "CORPORATE_RESIDENT",
        source="MANUAL",
    )
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    merged = {**base, **patch, "user_id": user_id, "transaction_id": transaction_id, "source": "MANUAL", "updated_at": _utcnow()}
    res = await run_db(
        lambda: sb.table("tax_transaction_classifications")
        .upsert(merged, on_conflict="user_id,transaction_id")
        .execute()
    )
    return (_rows(res) or [merged])[0]


async def _books_pnl_summary(user_id: str, start: date, end: date) -> dict[str, Any] | None:
    try:
        from app.services.qb_analytics_service import fetch_pnl_raw, is_qb_connected

        if not await is_qb_connected(user_id):
            return None
        raw = await fetch_pnl_raw(user_id, start.isoformat(), end.isoformat(), refresh=False)
        if not raw:
            return None
        # Best-effort parse of common QB report shapes
        income = 0.0
        expenses = 0.0
        sections = raw.get("sections") or raw.get("Rows") or []
        if isinstance(sections, list):
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                label = str(sec.get("section") or sec.get("label") or sec.get("group") or "").lower()
                amt = float(sec.get("amount") or sec.get("total") or 0)
                if "income" in label or "revenue" in label:
                    income += abs(amt)
                elif "expense" in label or "cost" in label:
                    expenses += abs(amt)
        net = income - expenses
        if income == 0 and expenses == 0:
            # fallback: metrics on report wrapper
            income = float(raw.get("total_income") or 0)
            expenses = float(raw.get("total_expenses") or 0)
            net = float(raw.get("net_profit") or income - expenses)
        return {"total_income": income, "total_expenses": expenses, "net_profit": net, "source": "quickbooks"}
    except Exception:
        return None


async def generate_return(user_id: str, req: TaxReturnGenerateRequest) -> dict[str, Any]:
    profile = await get_or_create_profile(user_id)
    classify_res = await classify_period(
        user_id,
        TaxClassifyRequest(
            date_from=req.period_start,
            date_to=req.period_end,
            account_ids=req.account_ids,
            persist=req.persist_classifications,
            reclassify_manual=False,
        ),
    )

    # Reload classifications + transactions for engine
    txns = await _fetch_transactions(user_id, req.period_start, req.period_end, req.account_ids)
    existing = await _existing_classifications(user_id, [t["id"] for t in txns if t.get("id")])
    counterparty = profile.get("default_wht_counterparty_type") or "CORPORATE_RESIDENT"
    paired: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for txn in txns:
        cls = existing.get(txn["id"])
        if not cls:
            cls = classify_transaction(txn, counterparty=counterparty)
        paired.append((txn, cls))

    books = None
    if req.include_books_pnl:
        books = await _books_pnl_summary(user_id, req.period_start, req.period_end)

    pack = compute_schedules(
        profile=profile,
        period_start=req.period_start,
        period_end=req.period_end,
        classified_rows=paired,
        books_pnl=books,
    )

    sb = get_supabase()
    # Supersede prior finalized overlapping packs of same type? Keep history; mark older DRAFT same period superseded optionally
    prior = await run_db(
        lambda: sb.table("tax_returns")
        .select("id")
        .eq("user_id", user_id)
        .eq("period_start", req.period_start.isoformat())
        .eq("period_end", req.period_end.isoformat())
        .eq("return_type", req.return_type)
        .eq("status", "DRAFT")
        .execute()
    )
    for row in _rows(prior):
        await run_db(
            lambda r=row: sb.table("tax_returns")
            .update({"status": "SUPERSEDED", "updated_at": _utcnow()})
            .eq("id", r["id"])
            .execute()
        )

    label = period_label(req.period_start, req.period_end)
    insert = {
        "user_id": user_id,
        "profile_id": profile.get("id"),
        "period_start": req.period_start.isoformat(),
        "period_end": req.period_end.isoformat(),
        "period_label": label,
        "return_type": req.return_type,
        "status": "DRAFT",
        "currency": profile.get("currency") or "NGN",
        "framework": FRAMEWORK_NAME,
        "report_json": pack,
        "summary_json": pack.get("summary") or {},
        "methodology_notes": "\n".join(pack["cover"].get("methodology") or []),
        "prepared_by": user_id,
        "prepared_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    created = await run_db(lambda: sb.table("tax_returns").insert(insert).execute())
    ret = (_rows(created) or [insert])[0]
    return_id = ret.get("id")

    if return_id:
        schedule_rows = []
        for sch in pack["schedules"]:
            schedule_rows.append(
                {
                    "return_id": return_id,
                    "user_id": user_id,
                    "schedule_code": sch["schedule_code"],
                    "schedule_title": sch["schedule_title"],
                    "sort_order": sch["sort_order"],
                    "totals_json": sch["totals_json"],
                    "lines_json": sch["lines_json"],
                    "notes": sch.get("notes"),
                }
            )
        for i in range(0, len(schedule_rows), 20):
            chunk = schedule_rows[i : i + 20]
            await run_db(lambda c=chunk: sb.table("tax_return_schedules").insert(c).execute())

    return {
        "return": ret,
        "report": pack,
        "classification_count": classify_res.get("count", 0),
        "references": statutory_reference_pack(),
    }


async def list_returns(user_id: str, limit: int = 24) -> list[dict[str, Any]]:
    sb = get_supabase()
    res = await run_db(
        lambda: sb.table("tax_returns")
        .select("id, period_start, period_end, period_label, return_type, status, summary_json, framework, created_at, finalized_at")
        .eq("user_id", user_id)
        .neq("status", "SUPERSEDED")
        .order("period_end", desc=True)
        .limit(limit)
        .execute()
    )
    return _rows(res)


async def get_return(user_id: str, return_id: str) -> dict[str, Any]:
    sb = get_supabase()
    res = await run_db(
        lambda: sb.table("tax_returns").select("*").eq("user_id", user_id).eq("id", return_id).limit(1).execute()
    )
    rows = _rows(res)
    if not rows:
        raise ValueError("Tax return not found")
    schedules = await run_db(
        lambda: sb.table("tax_return_schedules")
        .select("*")
        .eq("return_id", return_id)
        .order("sort_order")
        .execute()
    )
    return {"return": rows[0], "schedules": _rows(schedules), "references": statutory_reference_pack()}


async def update_return_status(user_id: str, return_id: str, status: str) -> dict[str, Any]:
    sb = get_supabase()
    patch: dict[str, Any] = {"status": status, "updated_at": _utcnow()}
    if status == "IN_REVIEW":
        patch["reviewed_by"] = user_id
        patch["reviewed_at"] = _utcnow()
    if status == "FINALIZED":
        patch["approved_by"] = user_id
        patch["finalized_at"] = _utcnow()
    res = await run_db(
        lambda: sb.table("tax_returns").update(patch).eq("user_id", user_id).eq("id", return_id).execute()
    )
    rows = _rows(res)
    if not rows:
        raise ValueError("Tax return not found")
    return rows[0]


def default_period_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = date(today.year, today.month, 1)
    end = date(today.year, today.month, monthrange(today.year, today.month)[1])
    # Prefer prior full month for filing packs
    if today.day < 25:
        if today.month == 1:
            start = date(today.year - 1, 12, 1)
            end = date(today.year - 1, 12, 31)
        else:
            m = today.month - 1
            start = date(today.year, m, 1)
            end = date(today.year, m, monthrange(today.year, m)[1])
    return start, end


async def export_return_csv(user_id: str, return_id: str) -> str:
    data = await get_return(user_id, return_id)
    report = data["return"].get("report_json") or {}
    schedules = report.get("schedules") or data.get("schedules") or []

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Whorl AI Nigeria Statutory Tax Report Pack"])
    writer.writerow(["Framework", FRAMEWORK_NAME])
    writer.writerow(["Return ID", return_id])
    writer.writerow([])

    cover = report.get("cover") or {}
    liab = cover.get("liabilities") or data["return"].get("summary_json") or {}
    writer.writerow(["LIABILITIES SUMMARY"])
    for k, v in liab.items():
        writer.writerow([k, v])
    writer.writerow([])

    for sch in schedules:
        code = sch.get("schedule_code") or sch.get("schedule_code")
        title = sch.get("schedule_title")
        writer.writerow([code, title])
        totals = sch.get("totals_json") or {}
        for k, v in totals.items():
            if not isinstance(v, (dict, list)):
                writer.writerow([k, v])
        lines = sch.get("lines_json")
        # normalize lines shapes
        flat: list[dict[str, Any]] = []
        if isinstance(lines, list):
            flat = [x for x in lines if isinstance(x, dict)]
        elif isinstance(lines, dict):
            for v in lines.values():
                if isinstance(v, list):
                    flat.extend([x for x in v if isinstance(x, dict)])
        if flat:
            headers = [
                "date", "description", "merchant", "type", "gross_amount", "net_amount",
                "vat_treatment", "vat_amount", "wht_category", "wht_amount", "cit_treatment",
            ]
            writer.writerow(headers)
            for line in flat:
                writer.writerow([line.get(h, "") for h in headers])
        writer.writerow([])

    return buf.getvalue()


async def export_return_json(user_id: str, return_id: str) -> dict[str, Any]:
    return await get_return(user_id, return_id)


async def framework_info() -> dict[str, Any]:
    start, end = default_period_bounds()
    return {
        "references": statutory_reference_pack(),
        "default_period_start": start.isoformat(),
        "default_period_end": end.isoformat(),
        "suggested_workflows": [
            "1. Complete taxpayer profile (TIN, RC, tax office, fixed assets).",
            "2. Classify period transactions (auto + manual review of low-confidence lines).",
            "3. Generate Combined Statutory Report Pack.",
            "4. Move status to In Review → Finalized after adviser sign-off.",
            "5. Export CSV / print PDF for FIRS presentation and remittance support.",
        ],
    }
