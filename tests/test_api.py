from unittest.mock import patch

import pytest

from custom_components.oura.api import (
    OuraApiClient,
    OuraApiError,
    OuraAuthError,
    OuraPermissionError,
    OuraRateLimitError,
)


async def test_pagination_preserves_query(api_session, response):
    api_session.async_request.side_effect = [
        response(body={"data": [{"id": "first"}], "next_token": "page2"}),
        response(body={"data": [{"id": "second"}], "next_token": None}),
    ]
    result = await OuraApiClient(api_session).async_get_collection(
        "vo2max", start_date="2026-10-01"
    )
    assert [item["id"] for item in result["data"]] == ["first", "second"]
    calls = api_session.async_request.call_args_list
    assert calls[0].args[1].endswith("/usercollection/vO2_max")
    assert calls[1].kwargs["params"] == {"start_date": "2026-10-01", "next_token": "page2"}


async def test_pagination_cycle_fails(api_session, response):
    api_session.async_request.return_value = response(body={"data": [], "next_token": "same"})
    with pytest.raises(OuraApiError, match="pagination"):
        await OuraApiClient(api_session).async_get_collection("sleep")
    assert api_session.async_request.await_count == 2


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, "invalid token", OuraAuthError),
        (403, "expired subscription", OuraPermissionError),
        (403, "missing scopes", OuraPermissionError),
        (404, "not found", OuraApiError),
    ],
)
async def test_http_errors_are_distinct(api_session, response, status, body, error):
    reply = response(status, body)
    api_session.async_request.return_value = reply
    with pytest.raises(error):
        await OuraApiClient(api_session).async_get_collection("sleep")
    reply.release.assert_called_once()
    assert api_session.async_request.await_count == 1


async def test_rate_limit_blocks_following_requests(api_session, response):
    api_session.async_request.return_value = response(429, headers={"Retry-After": "120"})
    client = OuraApiClient(api_session)
    for _ in range(2):
        with pytest.raises(OuraRateLimitError) as caught:
            await client.async_get_collection("sleep")
        assert 118 < caught.value.retry_after <= 120
    assert api_session.async_request.await_count == 1


async def test_transient_retry(api_session, response):
    api_session.async_request.side_effect = [response(503), response()]
    with patch("custom_components.oura.api.asyncio.sleep"):
        assert await OuraApiClient(api_session).async_get_collection("sleep") == {
            "data": [],
            "next_token": None,
        }
    assert api_session.async_request.await_count == 2


async def test_malformed_collection(api_session, response):
    api_session.async_request.return_value = response(body={"data": {"unexpected": True}})
    with pytest.raises(OuraApiError, match="invalid collection"):
        await OuraApiClient(api_session).async_get_collection("sleep")


async def test_sandbox_and_battery_latest(api_session, response):
    api_session.async_request.return_value = response()
    await OuraApiClient(api_session, use_sandbox=True).async_get_collection(
        "ring_battery_level", latest="true"
    )
    assert api_session.async_request.call_args.args[1].endswith(
        "/v2/sandbox/usercollection/ring_battery_level"
    )


async def test_revoked_refresh_token_is_authentication_failure(api_session):
    from aiohttp import ClientResponseError

    api_session.async_ensure_token_valid.side_effect = ClientResponseError(None, (), status=400)
    with pytest.raises(OuraAuthError):
        await OuraApiClient(api_session).async_ensure_token_valid()


async def test_network_timeout_is_bounded(api_session):
    api_session.async_request.side_effect = TimeoutError
    with patch("custom_components.oura.api.asyncio.sleep"), pytest.raises(OuraApiError):
        await OuraApiClient(api_session).async_get_collection("daily_sleep")
    assert api_session.async_request.await_count == 2


async def test_personal_info_is_not_a_paginated_collection(api_session, response):
    api_session.async_request.return_value = response(body={"id": "account-1"})
    assert await OuraApiClient(api_session).async_get_collection("personal_info") == {
        "id": "account-1"
    }
