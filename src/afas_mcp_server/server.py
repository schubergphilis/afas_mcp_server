"""The MCP server: tools that expose the connectors of one AFAS Profit environment to an AI agent."""

import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any, Literal, TypeVar

import httpx2
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from .client import AfasApiError, AfasClient, update_body
from .configuration import Settings
from .filters import Filter
from .validation import validate_element

PACKAGE_NAME = 'afas_mcp_server'
SERVER_NAME = 'afas-mcp-server'
LOGGER = logging.getLogger(__name__)

T = TypeVar('T')
Operation = Literal['insert', 'update']
ConnectorKind = Literal['all', 'get', 'update']
Element = dict[str, Any] | list[dict[str, Any]]

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)
DELETING = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)

READ_INSTRUCTIONS = """\
This server exposes one AFAS Profit environment through its REST connectors.

To read data:
1. afas_list_connectors finds GetConnectors (search by keyword; ids are technical names such as Profit_Employees).
2. afas_describe_get_connector lists the field ids, labels and data types of a connector.
3. afas_get_rows returns rows. Filter on field ids, not labels. Text operators add % wildcards themselves.
   Page with skip and take, and always pass order_by when paging so pages do not overlap.
afas_connection_info tells which environment you are connected to and whether the token works.
UpdateConnector schemas are available through afas_describe_update_connector, and afas_validate_payload checks a
payload against such a schema without sending anything.
"""

READ_ONLY_NOTICE = """
This server runs read-only: no tool can change data in AFAS. Ask the operator to start it with AFAS_ALLOW_WRITES=true
if changes are required.
"""

WRITE_INSTRUCTIONS = """
Writing is enabled. Before afas_insert or afas_update, call afas_describe_update_connector and afas_validate_payload,
show the user exactly what will change, and only then send it. afas_delete removes a record for good; confirm with
the user first. Field ids are case sensitive and key fields go on the Element as "@FieldId", not inside Fields.
"""

ConnectorId = Annotated[
    str, Field(description='Connector id as listed by afas_list_connectors, e.g. Profit_Employees.')
]
UpdateConnectorId = Annotated[
    str, Field(description='UpdateConnector id as listed by afas_list_connectors, e.g. KnSubject.')
]
ElementPayload = Annotated[
    Element,
    Field(
        description=(
            'The Element payload: {"Fields": {...}, "Objects": {...}} plus "@KeyField": value entries for updates. '
            'A list of such objects sends several records at once.'
        )
    ),
]


def package_version() -> str:
    """Return the installed version of this package, or 0.0.0 when it is not installed."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return '0.0.0'


@dataclass
class AppContext:
    """What every tool needs at request time."""

    settings: Settings
    client: AfasClient


ToolContext = Context[AppContext, Any]


def app_context(ctx: ToolContext) -> AppContext:
    """Return the shared settings and client that the lifespan created for this server."""
    return ctx.request_context.lifespan_context


def instructions_for(settings: Settings) -> str:
    """Compose the guidance the MCP client shows its model, depending on whether writes are enabled."""
    return READ_INSTRUCTIONS + (WRITE_INSTRUCTIONS if settings.allow_writes else READ_ONLY_NOTICE)


def describe_failure(error: AfasApiError) -> str:
    """Turn an AFAS error into a message the model can act on, including the internal detail when present."""
    internal = error.details.get('internalMessage')
    return f'{error} ({internal})' if internal and internal != error.details.get('externalMessage') else str(error)


async def call_afas(operation: Awaitable[T]) -> T:
    """Await an AFAS call, translating its errors into tool errors the model can read.

    Args:
        operation: The pending client call.

    Returns:
        The result of the call.

    Raises:
        ToolError: When AFAS rejected the call.
    """
    try:
        result = await operation
    except AfasApiError as error:
        raise ToolError(describe_failure(error)) from error
    return result


def matching(items: list[dict[str, Any]], search: str | None) -> list[dict[str, Any]]:
    """Keep the connectors whose id or description contains the search text, case-insensitively."""
    if not search:
        return list(items)
    needle = search.casefold()
    return [item for item in items if needle in f'{item.get("id", "")} {item.get("description", "")}'.casefold()]


async def connection_info(ctx: ToolContext) -> dict[str, Any]:
    """Show which AFAS environment this server talks to and confirm the token works by asking for the Profit version."""
    app = app_context(ctx)
    profit = await call_afas(app.client.profit_version())
    return {
        'base_url': app.settings.rest_base_url,
        'environment': app.settings.environment.value,
        'member_id': app.settings.member_id,
        'writes_enabled': app.settings.allow_writes,
        'profit_version': profit,
        'server_version': package_version(),
    }


async def list_connectors(
    ctx: ToolContext,
    *,
    kind: Annotated[
        ConnectorKind, Field(description='Which connectors to list: get (read), update (write) or all.')
    ] = 'all',
    search: Annotated[
        str | None, Field(description='Keep only connectors whose id or description contains this.')
    ] = None,
) -> dict[str, Any]:
    """List the GetConnectors and UpdateConnectors the configured token may use, optionally filtered by keyword."""
    app = app_context(ctx)
    catalog = await call_afas(app.client.list_connectors())
    get_connectors = matching(catalog.get('getConnectors', []), search) if kind != 'update' else []
    update_connectors = matching(catalog.get('updateConnectors', []), search) if kind != 'get' else []
    return {
        'get_connectors': get_connectors,
        'update_connectors': update_connectors,
        'get_connector_count': len(get_connectors),
        'update_connector_count': len(update_connectors),
    }


async def describe_get_connector(ctx: ToolContext, connector_id: ConnectorId) -> dict[str, Any]:
    """Describe a GetConnector: its field ids, labels, data types and lengths. Use the ids in filters and order_by."""
    return await call_afas(app_context(ctx).client.describe_get_connector(connector_id))


async def describe_update_connector(ctx: ToolContext, connector_id: UpdateConnectorId) -> dict[str, Any]:
    """Describe an UpdateConnector: its fields (mandatory, key, allowed values) and the nested objects it accepts."""
    return await call_afas(app_context(ctx).client.describe_update_connector(connector_id))


def check_page(skip: int, take: int, settings: Settings) -> None:
    """Reject paging parameters AFAS or the configured limits would not accept.

    Raises:
        ToolError: When skip is negative or take is outside 1..max_take.
    """
    if skip < 0:
        message = 'skip must be 0 or more'
        raise ToolError(message)
    if not 1 <= take <= settings.max_take:
        message = f'take must be between 1 and {settings.max_take}; page through larger result sets with skip'
        raise ToolError(message)


async def get_rows(
    ctx: ToolContext,
    connector_id: ConnectorId,
    *,
    skip: Annotated[int, Field(description='Number of rows to skip; combine with take to page.')] = 0,
    take: Annotated[int | None, Field(description='Rows to return; defaults to the configured page size.')] = None,
    filters: Annotated[
        list[Filter] | None,
        Field(description='Conditions on field ids. Same group = AND, different groups = OR.'),
    ] = None,
    order_by: Annotated[
        list[str] | None,
        Field(description='Field ids to sort on, prefix with - for descending. Required for reliable paging.'),
    ] = None,
) -> dict[str, Any]:
    """Read one page of rows from a GetConnector, with optional filters and sort order."""
    app = app_context(ctx)
    page_size = take if take is not None else app.settings.default_take
    check_page(skip, page_size, app.settings)
    rows = await call_afas(
        app.client.fetch_rows(connector_id, skip=skip, take=page_size, filters=filters, order_by=order_by)
    )
    has_more = len(rows) == page_size
    return {
        'connector_id': connector_id,
        'skip': skip,
        'take': page_size,
        'row_count': len(rows),
        'has_more': has_more,
        'next_skip': skip + page_size if has_more else None,
        'rows': rows,
    }


async def validate_payload(
    ctx: ToolContext,
    connector_id: UpdateConnectorId,
    element: ElementPayload,
    *,
    operation: Annotated[
        Operation, Field(description='insert requires all mandatory fields; update does not.')
    ] = 'insert',
) -> dict[str, Any]:
    """Check an UpdateConnector payload against the connector schema without sending it, and show the exact body."""
    app = app_context(ctx)
    schema = await call_afas(app.client.describe_update_connector(connector_id))
    issues = validate_element(schema, element, operation)
    return {
        'connector_id': connector_id,
        'operation': operation,
        'valid': not issues,
        'issues': [issue.model_dump() for issue in issues],
        'body': update_body(connector_id, element),
    }


async def ensure_valid(client: AfasClient, connector_id: str, element: Element, operation: Operation) -> None:
    """Fetch the connector schema and refuse the payload when it has problems.

    Raises:
        ToolError: Listing every problem found, so the model can fix them all at once.
    """
    schema = await call_afas(client.describe_update_connector(connector_id))
    issues = validate_element(schema, element, operation)
    if issues:
        listing = '; '.join(f'{issue.path}: {issue.message}' for issue in issues)
        message = f'{operation} payload for {connector_id} was not sent: {listing}'
        raise ToolError(message)


async def insert(
    ctx: ToolContext,
    connector_id: UpdateConnectorId,
    element: ElementPayload,
    *,
    validate: Annotated[bool, Field(description='Check the payload against the schema before sending.')] = True,
) -> dict[str, Any]:
    """Create records in AFAS through an UpdateConnector (HTTP POST)."""
    app = app_context(ctx)
    if validate:
        await ensure_valid(app.client, connector_id, element, 'insert')
    result = await call_afas(app.client.insert(connector_id, element))
    return {'connector_id': connector_id, 'operation': 'insert', 'result': result}


async def update(
    ctx: ToolContext,
    connector_id: UpdateConnectorId,
    element: ElementPayload,
    *,
    validate: Annotated[bool, Field(description='Check the payload against the schema before sending.')] = True,
) -> dict[str, Any]:
    """Change existing records in AFAS through an UpdateConnector (HTTP PUT); identify them with "@KeyField" entries."""
    app = app_context(ctx)
    if validate:
        await ensure_valid(app.client, connector_id, element, 'update')
    result = await call_afas(app.client.update(connector_id, element))
    return {'connector_id': connector_id, 'operation': 'update', 'result': result}


async def delete(
    ctx: ToolContext,
    connector_id: UpdateConnectorId,
    key_field: Annotated[str, Field(description='Primary key field id of the record, e.g. SbId.')],
    key_value: Annotated[str | int, Field(description='Value of the key field for the record to delete.')],
    *,
    object_name: Annotated[
        str | None,
        Field(description='Nested object to delete from; defaults to the connector itself.'),
    ] = None,
) -> dict[str, Any]:
    """Permanently delete one record in AFAS through an UpdateConnector (HTTP DELETE)."""
    app = app_context(ctx)
    result = await call_afas(app.client.delete(connector_id, key_field, key_value, object_name=object_name))
    return {
        'connector_id': connector_id,
        'operation': 'delete',
        'key_field': key_field,
        'key_value': key_value,
        'result': result,
    }


def register_read_tools(server: MCPServer) -> None:
    """Register the tools that never change data in AFAS."""
    server.add_tool(connection_info, name='afas_connection_info', title='AFAS connection info', annotations=READ_ONLY)
    server.add_tool(list_connectors, name='afas_list_connectors', title='List AFAS connectors', annotations=READ_ONLY)
    server.add_tool(
        describe_get_connector,
        name='afas_describe_get_connector',
        title='Describe a GetConnector',
        annotations=READ_ONLY,
    )
    server.add_tool(
        describe_update_connector,
        name='afas_describe_update_connector',
        title='Describe an UpdateConnector',
        annotations=READ_ONLY,
    )
    server.add_tool(get_rows, name='afas_get_rows', title='Read rows from a GetConnector', annotations=READ_ONLY)
    server.add_tool(
        validate_payload,
        name='afas_validate_payload',
        title='Validate an UpdateConnector payload',
        annotations=READ_ONLY,
    )


def register_write_tools(server: MCPServer) -> None:
    """Register the tools that create, change or delete data in AFAS."""
    server.add_tool(insert, name='afas_insert', title='Insert records', annotations=ADDITIVE)
    server.add_tool(update, name='afas_update', title='Update records', annotations=DESTRUCTIVE)
    server.add_tool(delete, name='afas_delete', title='Delete a record', annotations=DELETING)


def build_server(settings: Settings | None = None, transport: httpx2.AsyncBaseTransport | None = None) -> MCPServer:
    """Create the MCP server for one AFAS environment.

    Args:
        settings: Connection settings; read from the environment when omitted.
        transport: Optional HTTP transport for the AFAS client, used by tests to fake AFAS.

    Returns:
        A server with the read tools, and the write tools when the settings allow writes.
    """
    resolved = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        async with AfasClient(resolved, transport=transport) as client:
            LOGGER.info('connected to %s (writes %s)', resolved.rest_base_url, 'on' if resolved.allow_writes else 'off')
            yield AppContext(settings=resolved, client=client)

    server = MCPServer(
        name=SERVER_NAME,
        version=package_version(),
        instructions=instructions_for(resolved),
        lifespan=lifespan,
    )
    register_read_tools(server)
    if resolved.allow_writes:
        register_write_tools(server)
    return server
