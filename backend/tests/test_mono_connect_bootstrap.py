"""Tests for Mono connect synthetic feed bootstrap."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_connect_mono_bootstraps_synthetic_feed():
    account = {"id": "acct-1", "account_name": "GTBank", "provider": "mono"}
    bootstrap = {"created": 125, "filled": True, "live_started": True}

    with patch(
        "app.services.mono_service.settings.mono_secret_key",
        "test_secret",
    ), patch(
        "app.config.Settings.synthetic_feed_allowed",
        new_callable=lambda: property(lambda self: True),
    ), patch(
        "app.services.mono_service._exchange_code",
        AsyncMock(return_value="mono-1"),
    ), patch(
        "app.services.mono_service._fetch_account_details",
        AsyncMock(return_value={"account": {"institution": {"name": "GTBank"}}}),
    ), patch(
        "app.services.mono_service.connect_or_reactivate_bank_account",
        AsyncMock(return_value=(account, False)),
    ), patch(
        "app.services.mono_service.encrypt_token",
        return_value="enc",
    ), patch(
        "app.services.synthetic_feed_service.bootstrap_feed_on_mono_connect",
        AsyncMock(return_value=bootstrap),
    ) as bootstrap_fn:
        from app.services.mono_service import connect_mono_account

        result = await connect_mono_account("user-1", "auth-code", "Mono Account")

    bootstrap_fn.assert_awaited_once_with("user-1", "acct-1")
    assert result["feed_bootstrap"]["created"] == 125
    assert result["id"] == "acct-1"


@pytest.mark.asyncio
async def test_bootstrap_feed_fills_when_empty_then_starts_live():
    with patch(
        "app.services.synthetic_feed_service.synthetic_feed_allowed",
        return_value=True,
    ), patch(
        "app.services.synthetic_feed_service._get_mono_account",
        AsyncMock(return_value={"id": "acct-1"}),
    ), patch(
        "app.services.synthetic_feed_service.get_or_create_profile",
        AsyncMock(return_value={"id": "prof-1"}),
    ), patch(
        "app.services.synthetic_feed_service.maybe_enforce_synthetic_wins",
        AsyncMock(return_value=0),
    ), patch(
        "app.services.synthetic_feed_service.transaction_stats",
        AsyncMock(return_value={"synthetic": 0, "total": 0}),
    ), patch(
        "app.services.synthetic_feed_service.fill_sparse_history",
        AsyncMock(return_value={"created": 100}),
    ) as fill, patch(
        "app.services.synthetic_feed_service.start_live_feed",
        AsyncMock(return_value={"first_drip": {"created": 3}, "interval_hours": 6}),
    ) as live:
        from app.services.synthetic_feed_service import bootstrap_feed_on_mono_connect

        result = await bootstrap_feed_on_mono_connect("user-1", "acct-1")

    fill.assert_awaited_once()
    live.assert_awaited_once_with("user-1", "acct-1")
    assert result is not None
    assert result["filled"] is True
    assert result["created"] == 103
    assert result["live_started"] is True


@pytest.mark.asyncio
async def test_bootstrap_skips_fill_when_synthetic_exists():
    with patch(
        "app.services.synthetic_feed_service.synthetic_feed_allowed",
        return_value=True,
    ), patch(
        "app.services.synthetic_feed_service._get_mono_account",
        AsyncMock(return_value={"id": "acct-1"}),
    ), patch(
        "app.services.synthetic_feed_service.get_or_create_profile",
        AsyncMock(return_value={"id": "prof-1"}),
    ), patch(
        "app.services.synthetic_feed_service.maybe_enforce_synthetic_wins",
        AsyncMock(return_value=0),
    ), patch(
        "app.services.synthetic_feed_service.transaction_stats",
        AsyncMock(return_value={"synthetic": 40, "total": 40}),
    ), patch(
        "app.services.synthetic_feed_service.fill_sparse_history",
        AsyncMock(),
    ) as fill, patch(
        "app.services.synthetic_feed_service.start_live_feed",
        AsyncMock(return_value={"first_drip": {"created": 2}, "interval_hours": 6}),
    ):
        from app.services.synthetic_feed_service import bootstrap_feed_on_mono_connect

        result = await bootstrap_feed_on_mono_connect("user-1", "acct-1")

    fill.assert_not_awaited()
    assert result is not None
    assert result["skipped_fill"] is True
    assert result["created"] == 2
