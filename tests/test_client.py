"""Tests for the AFAS REST client against a fake transport."""

import base64
import json
from typing import Any

import httpx2
import pytest

from afas_mcp_server.client import (
    AfasApiError,
    AfasClient,
    connector_path,
    decode_profit_error_header,
    update_body,
)
from afas_mcp_server.filters import Filter, Operator
from tests.conftest import make_settings


class FakeAfas:
    """Records requests and answers each with a canned response."""

    def __init__(self, response: httpx2.Response | None = None) -> None:
        """Answer every request with ``response`` (an empty ``{}`` document by default)."""
        self.response = response or httpx2.Response(200, json={})
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Record the request and return the canned response."""
        self.requests.append(request)
        return self.response

    @property
    def last(self) -> httpx2.Request:
        """The most recent request."""
        return self.requests[-1]


def make_client(fake: FakeAfas, **overrides: Any) -> AfasClient:  # noqa: ANN401
    """Build a client whose HTTP traffic goes to ``fake`` instead of the network."""
    return AfasClient(make_settings(**overrides), transport=httpx2.MockTransport(fake))


def test_connector_path_encodes_segments_but_keeps_at_sign() -> None:
    """The delete path needs a literal @ before the key field, everything else is percent-encoded."""
    assert (
        connector_path('KnSubject', 'KnSubject', '@SbId', 'a b/c') == 'connectors/KnSubject/KnSubject/@SbId/a%20b%2Fc'
    )


def test_update_body_wraps_element_in_connector_envelope() -> None:
    """AFAS expects {connector: {Element: ...}}."""
    assert update_body('KnSubject', {'Fields': {'Ds': 'x'}}) == {'KnSubject': {'Element': {'Fields': {'Ds': 'x'}}}}


def test_decode_profit_error_header_handles_json_text_and_garbage() -> None:
    """The header is base64; inside it is JSON if we are lucky, text otherwise."""
    encoded_json = base64.b64encode(b'{"externalMessage": "Boom"}').decode()
    encoded_text = base64.b64encode(b'plain failure').decode()
    assert decode_profit_error_header(encoded_json) == {'externalMessage': 'Boom'}
    assert decode_profit_error_header(encoded_text) == {'profitError': 'plain failure'}
    assert decode_profit_error_header('not base64!') == {'profitError': 'not base64!'}


@pytest.mark.anyio
async def test_requests_carry_token_and_language() -> None:
    """Every call authenticates with the AfasToken header and asks for the configured language."""
    fake = FakeAfas(httpx2.Response(200, json={'version': '1'}))
    async with make_client(fake, language='en-us') as client:
        assert await client.profit_version() == {'version': '1'}
    assert fake.last.headers['Authorization'] == client.settings.authorization_header
    assert fake.last.headers['Accept-Language'] == 'en-us'
    assert fake.last.headers['Accept'] == 'application/json'
    assert fake.last.url.path == '/profitrestservices/profitversion'


@pytest.mark.anyio
async def test_fetch_rows_builds_url_and_returns_rows() -> None:
    """Rows come back as a list; paging, filters and sorting end up in the query string."""
    fake = FakeAfas(httpx2.Response(200, json={'skip': 0, 'take': 2, 'rows': [{'Id': 1}, {'Id': 2}]}))
    async with make_client(fake) as client:
        rows = await client.fetch_rows(
            'Profit_Employees',
            skip=0,
            take=2,
            filters=[Filter(field='City', operator=Operator.CONTAINS, value='dam')],
            order_by=['-Id'],
        )
    assert rows == [{'Id': 1}, {'Id': 2}]
    assert fake.last.method == 'GET'
    assert fake.last.url.host == '12345.rest.afas.online'
    assert fake.last.url.path == '/profitrestservices/connectors/Profit_Employees'
    assert dict(fake.last.url.params) == {
        'skip': '0',
        'take': '2',
        'filterfieldids': 'City',
        'filtervalues': '%dam%',
        'operatortypes': '6',
        'orderbyfieldids': '-Id',
    }


@pytest.mark.anyio
async def test_fetch_rows_defaults_take_to_settings() -> None:
    """Without an explicit page size the configured default is used."""
    fake = FakeAfas(httpx2.Response(200, json={'rows': []}))
    async with make_client(fake, default_take=25) as client:
        assert await client.fetch_rows('Profit_Employees') == []
    assert fake.last.url.params['take'] == '25'


@pytest.mark.anyio
async def test_fetch_rows_tolerates_missing_rows_key() -> None:
    """An unexpected body without rows yields an empty page rather than a crash."""
    fake = FakeAfas(httpx2.Response(200, json={}))
    async with make_client(fake) as client:
        assert await client.fetch_rows('Profit_Employees') == []


@pytest.mark.anyio
async def test_metainfo_paths() -> None:
    """The three metainfo calls hit their documented paths."""
    fake = FakeAfas(httpx2.Response(200, json={'fields': []}))
    async with make_client(fake) as client:
        await client.list_connectors()
        assert fake.last.url.path == '/profitrestservices/metainfo'
        await client.describe_get_connector('Profit_Employees')
        assert fake.last.url.path == '/profitrestservices/metainfo/get/Profit_Employees'
        await client.describe_update_connector('KnSubject')
        assert fake.last.url.path == '/profitrestservices/metainfo/update/KnSubject'


@pytest.mark.anyio
async def test_base_url_override_is_respected() -> None:
    """A custom base URL (proxy or on-premise) replaces the AFAS Online hostname."""
    fake = FakeAfas()
    async with make_client(fake, member_id=None, base_url='https://proxy.example.test/afas') as client:
        await client.list_connectors()
    assert str(fake.last.url) == 'https://proxy.example.test/afas/metainfo'


@pytest.mark.anyio
async def test_insert_posts_wrapped_json_as_utf8() -> None:
    """Inserts POST the connector envelope with the charset AFAS insists on."""
    fake = FakeAfas(httpx2.Response(201, json={'results': {'KnSubject': {'SbId': 7}}}))
    async with make_client(fake) as client:
        result = await client.insert('KnSubject', {'Fields': {'Ds': 'Café'}})
    assert result == {'results': {'KnSubject': {'SbId': 7}}}
    assert fake.last.method == 'POST'
    assert fake.last.url.path == '/profitrestservices/connectors/KnSubject'
    assert fake.last.headers['Content-Type'] == 'application/json;charset=utf-8'
    assert json.loads(fake.last.content.decode('utf-8')) == {'KnSubject': {'Element': {'Fields': {'Ds': 'Café'}}}}


@pytest.mark.anyio
async def test_update_puts_and_accepts_empty_response() -> None:
    """Updates PUT the same envelope; AFAS often answers with no body."""
    fake = FakeAfas(httpx2.Response(200))
    async with make_client(fake) as client:
        result = await client.update('KnSubject', {'@SbId': 7, 'Fields': {'Ds': 'x'}})
    assert result is None
    assert fake.last.method == 'PUT'
    assert json.loads(fake.last.content) == {'KnSubject': {'Element': {'@SbId': 7, 'Fields': {'Ds': 'x'}}}}


@pytest.mark.anyio
async def test_delete_builds_documented_path() -> None:
    """Deletes address the record by connector, element, @key field and value."""
    fake = FakeAfas(httpx2.Response(200))
    async with make_client(fake) as client:
        await client.delete('KnSubject', 'SbId', 2)
        assert fake.last.method == 'DELETE'
        assert fake.last.url.path == '/profitrestservices/connectors/KnSubject/KnSubject/@SbId/2'
        await client.delete('KnSubject', '@SbId', '3', object_name='KnSubjectLink')
        assert fake.last.url.path == '/profitrestservices/connectors/KnSubject/KnSubjectLink/@SbId/3'


@pytest.mark.anyio
async def test_json_error_body_becomes_api_error() -> None:
    """AFAS error bodies carry externalMessage; it becomes the exception message."""
    body = {'errorNumber': -2147180996, 'externalMessage': 'Ongeldige token', 'internalMessage': 'detail'}
    fake = FakeAfas(httpx2.Response(401, json=body))
    async with make_client(fake) as client:
        with pytest.raises(AfasApiError, match='HTTP 401: Ongeldige token') as caught:
            await client.list_connectors()
    assert caught.value.status_code == 401
    assert caught.value.method == 'GET'
    assert caught.value.details['internalMessage'] == 'detail'


@pytest.mark.anyio
async def test_profit_error_header_is_decoded_into_details() -> None:
    """The base64 X-PROFIT-ERROR header is merged into the error details."""
    header = base64.b64encode(b'{"externalMessage": "Business rule failed"}').decode()
    fake = FakeAfas(httpx2.Response(500, headers={'X-PROFIT-ERROR': header}))
    async with make_client(fake) as client:
        with pytest.raises(AfasApiError, match='Business rule failed'):
            await client.insert('KnSubject', {'Fields': {}})


@pytest.mark.anyio
async def test_plain_text_error_body_is_kept() -> None:
    """Non-JSON error bodies are surfaced as the message."""
    fake = FakeAfas(httpx2.Response(404, text='Connector not found'))
    async with make_client(fake) as client:
        with pytest.raises(AfasApiError, match='Connector not found'):
            await client.describe_get_connector('Nope')


@pytest.mark.anyio
async def test_error_without_any_detail_still_names_the_call() -> None:
    """Even an empty error response produces an actionable message."""
    fake = FakeAfas(httpx2.Response(503))
    async with make_client(fake) as client:
        with pytest.raises(AfasApiError, match=r'GET .*metainfo failed with HTTP 503: AFAS returned an error'):
            await client.list_connectors()
