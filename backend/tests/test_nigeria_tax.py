"""Unit tests for Nigeria tax classifier and statutory engine (NTA 2025)."""

from datetime import date

from app.services.tax.nigeria_classifier import classify_transaction
from app.services.tax.nigeria_constants import (
    DEVELOPMENT_LEVY_RATE,
    VAT_RATE,
    cit_rate_for_band,
    company_size_band,
    wht_rate_for,
)
from app.services.tax.nigeria_engine import compute_schedules, filing_due_date


def test_vat_rate_is_seven_point_five():
    assert VAT_RATE == 0.075


def test_small_company_band_and_cit_rate():
    assert company_size_band(50_000_000, 100_000_000) == "SMALL"
    assert cit_rate_for_band("SMALL") == 0.0
    assert company_size_band(150_000_000, 100_000_000) == "LARGE"
    assert cit_rate_for_band("LARGE") == 0.30


def test_wht_professional_resident_corporate():
    assert wht_rate_for("PROFESSIONAL", "CORPORATE_RESIDENT") == 0.05
    assert wht_rate_for("DIVIDENDS", "CORPORATE_RESIDENT") == 0.10


def test_classify_vat_on_nip():
    cls = classify_transaction(
        {
            "description": "VAT ON NIP TRANSFER",
            "amount": 37.5,
            "transaction_type": "debit",
            "category": "Fees",
        }
    )
    assert cls["vat_treatment"] == "BANK_CHARGE_VAT"
    assert cls["vat_amount"] == 37.5


def test_classify_professional_fee_debit_splits_vat_and_wht():
    cls = classify_transaction(
        {
            "description": "Payment for consultancy advisory retainer",
            "merchant_name": "Apex Advisory Ltd",
            "amount": 107500,
            "transaction_type": "debit",
            "category": "Professional",
        }
    )
    assert cls["vat_treatment"] == "STANDARD_INPUT"
    assert cls["wht_category"] == "PROFESSIONAL"
    assert cls["wht_role"] == "AGENT_DEDUCTED"
    assert cls["vat_amount"] > 0
    assert cls["wht_amount"] > 0


def test_classify_interest_credit():
    cls = classify_transaction(
        {
            "description": "Credit interest",
            "amount": 5000,
            "transaction_type": "credit",
            "category": "Interest",
        }
    )
    assert cls["cit_treatment"] == "TAXABLE_INCOME"
    assert cls["wht_category"] == "INTEREST"


def test_filing_due_date_next_month_21():
    assert filing_due_date(date(2026, 3, 31)) == date(2026, 4, 21)


def test_compute_schedules_produces_firs_pack():
    profile = {
        "legal_name": "Elumelu Demo Holdings Ltd",
        "tin": "12345678-0001",
        "rc_number": "RC123456",
        "entity_type": "COMPANY",
        "fixed_assets_ngn": 300_000_000,
        "currency": "NGN",
        "vat_registered": True,
    }
    revenue = {
        "id": "t1",
        "transaction_date": "2026-03-05",
        "description": "Client service receipt",
        "merchant_name": "Client A",
        "category": "Sales",
        "amount": 1_075_000,
        "transaction_type": "credit",
        "currency": "NGN",
    }
    expense = {
        "id": "t2",
        "transaction_date": "2026-03-10",
        "description": "Consultancy professional fee",
        "merchant_name": "Advisor",
        "category": "Professional",
        "amount": 215_000,
        "transaction_type": "debit",
        "currency": "NGN",
    }
    paired = [
        (revenue, classify_transaction(revenue)),
        (expense, classify_transaction(expense)),
    ]
    pack = compute_schedules(
        profile=profile,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        classified_rows=paired,
        books_pnl={"total_income": 5_000_000, "total_expenses": 2_000_000, "net_profit": 3_000_000},
    )
    assert pack["cover"]["document_title"]
    codes = {s["schedule_code"] for s in pack["schedules"]}
    assert {"VAT_01", "WHT_01", "CIT_01", "DEV_01"}.issubset(codes)
    assert pack["summary"]["size_band"] == "LARGE"
    assert pack["liabilities"]["development_levy_payable"] == round(3_000_000 * DEVELOPMENT_LEVY_RATE, 2)
    assert pack["liabilities"]["cit_payable"] == round(3_000_000 * 0.30, 2)
