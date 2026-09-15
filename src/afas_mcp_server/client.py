"""Thin asynchronous client for the AFAS Profit REST services."""

import base64
import binascii
import json
import logging
from typing import Any
from urllib.parse import quote

import httpx2
from typing_extensions import Self

from .configuration import Settings
from .filters import Filter, query_params

HTTP_ERROR_THRESHOLD = 400
PROFIT_ERROR_HEADER = 'X-PROFIT-ERROR'
JSON_CONTENT_TYPE = 'application/json;charset=utf-8'
ELEMENT_KEY = 'Element'
KEY_PREFIX = '@'


class AfasError(Exception):
    """Base class for errors raised by the AFAS client."""


class AfasApiError(AfasError):
    """An HTTP error response from the AFAS REST services, with the Profit error details decoded."""

    def __init__(self, status_code: int, method: str, url: str, details: dict[str, Any]) -> None:
        """Record the failed call and the details AFAS returned about it.

        Args:
            status_code: The HTTP status code.
            method: The HTTP method of the failed call.
            url: The URL of the failed call.
            details: Error information decoded from the body and the ``X-PROFIT-ERROR`` header.
        """
        self.status_code = status_code
        self.method = method
        self.url = url
        self.details = details
        super().__init__(self.describe())

    def describe(self) -> str:
        """Return a one-line human readable summary of the failure."""
        message = self.details.get('externalMessage') or self.details.get('message') or 'AFAS returned an error'
        return f'{self.method} {self.url} failed with HTTP {self.status_code}: {message}'


def decode_profit_error_header(value: str) -> dict[str, Any]:
    """Decode the base64 ``X-PROFIT-ERROR`` header AFAS adds to failed calls.

    Args:
        value: The raw header value.

    Returns:
        The decoded JSON object, or the decoded text under ``profitError`` when it is not JSON.
    """
    try:
        text = base64.b64decode(value, validate=True).decode('utf-8', errors='replace')
    except (binascii.Error, ValueError):
        return {'profitError': value}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {'profitError': text}
    return parsed if isinstance(parsed, dict) else {'profitError': parsed}


def parse_json(response: httpx2.Response) -> Any:  # noqa: ANN401
    """Return the JSON body of a response, or None when there is none.

    Args:
        response: The HTTP response.

    Returns:
        The decoded JSON value, or None for an empty or non-JSON body.
    """
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def error_details(response: httpx2.Response) -> dict[str, Any]:
    """Collect everything AFAS tells us about a failed call.

    Args:
        response: The error response.

    Returns:
        The ``X-PROFIT-ERROR`` header and JSON body merged, or the plain text body under ``message``.
    """
    details: dict[str, Any] = {}
    header = response.headers.get(PROFIT_ERROR_HEADER)
    if header:
        details.update(decode_profit_error_header(header))
    body = parse_json(response)
    if isinstance(body, dict):
        details.update(body)
    elif response.text.strip():
        details.setdefault('message', response.text.strip())
    return details


def update_body(connector_id: str, element: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap an element in the envelope UpdateConnectors expect.

    Args:
        connector_id: The UpdateConnector id, e.g. ``KnSubject``.
        element: The ``Element`` payload with ``Fields`` and optional ``Objects``.

    Returns:
        The request body ``{connector_id: {"Element": element}}``.
    """
    return {connector_id: {ELEMENT_KEY: element}}


def connector_path(*segments: str) -> str:
    """Join path segments under ``connectors/``, percent-encoding everything but ``@``.

    Args:
        segments: The path segments after ``connectors``.

    Returns:
        The relative request path.
    """
    return '/'.join(['connectors', *(quote(segment, safe='@') for segment in segments)])


class AfasClient:
    """Asynchronous access to GetConnectors, UpdateConnectors and metainfo of one AFAS environment.

    Use it as an async context manager so the underlying HTTP connection pool is closed.
    """

    def __init__(self, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        """Prepare an HTTP client with the AFAS token and base URL from the settings.

        Args:
            settings: Connection settings.
            transport: Optional HTTP transport, used by tests to fake AFAS.
        """
        self._logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        self.settings = settings
        self._http = httpx2.AsyncClient(
            base_url=settings.rest_base_url,
            headers={
                'Authorization': settings.authorization_header,
                'Accept': 'application/json',
                'Accept-Language': settings.language,
            },
            timeout=httpx2.Timeout(settings.timeout_seconds),
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        """Enter the context; the client is ready to use as soon as it is constructed."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Close the HTTP connection pool."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:  # noqa: ANN401
        """Send one request to AFAS and return its decoded JSON body.

        Args:
            method: HTTP method.
            path: Path relative to the REST services base URL.
            params: Query parameters.
            body: JSON body for POST and PUT.

        Returns:
            The decoded JSON response, or None when AFAS sent no body.

        Raises:
            AfasApiError: When AFAS answers with an HTTP error status.
        """
        content = None
        headers = {}
        if body is not None:
            content = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = JSON_CONTENT_TYPE
        self._logger.debug('%s %s params=%s', method, path, params)
        response = await self._http.request(method, path, params=params, content=content, headers=headers)
        if response.status_code >= HTTP_ERROR_THRESHOLD:
            raise AfasApiError(response.status_code, method, str(response.request.url), error_details(response))
        return parse_json(response)

    async def profit_version(self) -> dict[str, Any]:
        """Return the Profit version information, which doubles as a connectivity and token check."""
        return await self.request('GET', 'profitversion') or {}

    async def list_connectors(self) -> dict[str, Any]:
        """Return the GetConnectors and UpdateConnectors the token may use, as AFAS reports them."""
        return await self.request('GET', 'metainfo') or {}

    async def describe_get_connector(self, connector_id: str) -> dict[str, Any]:
        """Return the field definitions of a GetConnector.

        Args:
            connector_id: The GetConnector id.

        Returns:
            The metainfo document with ``name``, ``description`` and ``fields``.
        """
        return await self.request('GET', f'metainfo/get/{quote(connector_id, safe="")}') or {}

    async def describe_update_connector(self, connector_id: str) -> dict[str, Any]:
        """Return the schema of an UpdateConnector, including nested objects.

        Args:
            connector_id: The UpdateConnector id.

        Returns:
            The metainfo document with ``fields`` and ``objects``.
        """
        return await self.request('GET', f'metainfo/update/{quote(connector_id, safe="")}') or {}

    async def fetch_rows(
        self,
        connector_id: str,
        *,
        skip: int = 0,
        take: int | None = None,
        filters: list[Filter] | None = None,
        order_by: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return one page of rows from a GetConnector.

        Args:
            connector_id: The GetConnector id.
            skip: Number of rows to skip.
            take: Number of rows to return; defaults to the configured page size.
            filters: Conditions to apply.
            order_by: Sort order; prefix a field with ``-`` for descending.

        Returns:
            The rows of the page, each a mapping of field id to value.
        """
        params = query_params(
            skip=skip,
            take=take if take is not None else self.settings.default_take,
            filters=filters,
            order_by=order_by,
        )
        payload = await self.request('GET', connector_path(connector_id), params=params) or {}
        return list(payload.get('rows', []))

    async def insert(self, connector_id: str, element: dict[str, Any] | list[dict[str, Any]]) -> Any:  # noqa: ANN401
        """Create records through an UpdateConnector.

        Args:
            connector_id: The UpdateConnector id.
            element: The ``Element`` payload.

        Returns:
            Whatever AFAS returns, usually the keys of the created records.
        """
        return await self.request('POST', connector_path(connector_id), body=update_body(connector_id, element))

    async def update(self, connector_id: str, element: dict[str, Any] | list[dict[str, Any]]) -> Any:  # noqa: ANN401
        """Change existing records through an UpdateConnector.

        Args:
            connector_id: The UpdateConnector id.
            element: The ``Element`` payload, including the ``@Key`` entries that identify the records.

        Returns:
            Whatever AFAS returns, often nothing.
        """
        return await self.request('PUT', connector_path(connector_id), body=update_body(connector_id, element))

    async def delete(
        self,
        connector_id: str,
        key_field: str,
        key_value: str | int,
        object_name: str | None = None,
    ) -> Any:  # noqa: ANN401
        """Delete one record through an UpdateConnector.

        Args:
            connector_id: The UpdateConnector id.
            key_field: The key field, with or without the leading ``@``.
            key_value: The key value of the record to delete.
            object_name: The element to delete from; defaults to the connector itself.

        Returns:
            Whatever AFAS returns, often nothing.
        """
        field = key_field if key_field.startswith(KEY_PREFIX) else f'{KEY_PREFIX}{key_field}'
        path = connector_path(connector_id, object_name or connector_id, field, str(key_value))
        return await self.request('DELETE', path)
