"""Tests for the MCP server wiring, driven through an in-process MCP client against a fake AFAS."""

# pylint: disable=redefined-outer-name  # pytest fixtures are injected by parameter name

from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent

from afas_mcp_server import server as server_module
from afas_mcp_server.client import AfasApiError
from afas_mcp_server.server import build_server, describe_failure, instructions_for, matching, package_version
from tests.conftest import UPDATE_SCHEMA, make_settings

READ_TOOLS = {
    'afas_connection_info',
    'afas_list_connectors',
    'afas_describe_get_connector',
    'afas_describe_update_connector',
    'afas_get_rows',
    'afas_validate_payload',
}
WRITE_TOOLS = {'afas_insert', 'afas_update', 'afas_delete'}
EMPLOYEES = [{'Id': 1, 'Name': 'Jan'}, {'Id': 2, 'Name': 'Piet'}, {'Id': 3, 'Name': 'Klaas'}]
EMPLOYEE_FIELDS = {
    'name': 'Profit_Employees',
    'description': 'Medewerkers',
    'fields': [{'id': 'Id', 'fieldId': 'Id', 'dataType': 'int', 'label': 'Nummer', 'length': 0}],
}
CATALOG = {
    'getConnectors': [
        {'id': 'Profit_Employees', 'description': 'Medewerkers'},
        {'id': 'Profit_Debtors', 'description': 'Debiteuren'},
    ],
    'updateConnectors': [{'id': 'KnSubject', 'description': 'Dossieritem'}],
}
STATIC_ROUTES: dict[str, Any] = {
    'profitversion': {'version': '2026.1'},
    'metainfo': CATALOG,
    'metainfo/get/Profit_Employees': EMPLOYEE_FIELDS,
    'metainfo/update/KnSubject': UPDATE_SCHEMA,
}


def error_text(result: CallToolResult) -> str:
    """The text of a tool error, which the SDK always delivers as a single text block."""
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


class FakeAfasApi:
    """A tiny AFAS: a version endpoint, a catalog, one GetConnector and one UpdateConnector."""

    def __init__(self) -> None:
        """Start with no recorded requests."""
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Route the request the way the real REST services would."""
        self.requests.append(request)
        path = request.url.path.removeprefix('/profitrestservices/')
        if path in STATIC_ROUTES:
            return httpx2.Response(200, json=STATIC_ROUTES[path])
        if path == 'connectors/Profit_Employees':
            return self.page(request)
        if path.startswith('connectors/KnSubject'):
            return self.write(request)
        return httpx2.Response(404, json={'externalMessage': 'Onbekende connector', 'internalMessage': 'no such id'})

    @staticmethod
    def page(request: httpx2.Request) -> httpx2.Response:
        """Apply skip and take to the employee rows."""
        skip = int(request.url.params.get('skip', '0'))
        take = int(request.url.params.get('take', '100'))
        return httpx2.Response(200, json={'skip': skip, 'take': take, 'rows': EMPLOYEES[skip : skip + take]})

    @staticmethod
    def write(request: httpx2.Request) -> httpx2.Response:
        """Answer inserts with the new key and updates and deletes with an empty body."""
        if request.method == 'POST':
            return httpx2.Response(201, json={'results': {'KnSubject': {'SbId': 42}}})
        return httpx2.Response(200)

    def calls(self, method: str) -> list[httpx2.Request]:
        """The recorded requests with the given HTTP method."""
        return [request for request in self.requests if request.method == method]


@pytest.fixture
def afas() -> FakeAfasApi:
    """A fresh fake AFAS per test."""
    return FakeAfasApi()


def server_for(afas: FakeAfasApi, **overrides: Any) -> MCPServer:  # noqa: ANN401
    """Build a server whose AFAS traffic goes to the fake."""
    return build_server(make_settings(**overrides), transport=httpx2.MockTransport(afas))


def test_instructions_reflect_write_mode() -> None:
    """The model is told whether the server can change data."""
    assert 'read-only' in instructions_for(make_settings())
    assert 'Writing is enabled' in instructions_for(make_settings(allow_writes=True))


def test_package_version_falls_back_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running from a plain checkout without installing still yields a version string."""

    def missing(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(server_module, 'version', missing)
    assert package_version() == '0.0.0'


def test_build_server_reads_settings_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without explicit settings the server configures itself from AFAS_* variables, as the CLI does."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('AFAS_MEMBER_ID', '777')
    monkeypatch.setenv('AFAS_TOKEN', 'ABC')
    monkeypatch.setenv('AFAS_ALLOW_WRITES', 'true')
    server = build_server()
    assert server.instructions is not None
    assert 'Writing is enabled' in server.instructions


def test_matching_is_case_insensitive_on_id_and_description() -> None:
    """A keyword matches either the technical id or the human description."""
    items = CATALOG['getConnectors']
    assert matching(items, 'MEDEW') == [items[0]]
    assert matching(items, 'debtors') == [items[1]]
    assert matching(items, None) == items


def test_describe_failure_adds_internal_message_when_it_differs() -> None:
    """The internal message often names the actual cause, so it is appended when it adds information."""
    same = AfasApiError(400, 'GET', 'u', {'externalMessage': 'Fout', 'internalMessage': 'Fout'})
    different = AfasApiError(400, 'GET', 'u', {'externalMessage': 'Fout', 'internalMessage': 'veld X ontbreekt'})
    assert describe_failure(same) == str(same)
    assert describe_failure(different) == f'{different} (veld X ontbreekt)'


@pytest.mark.anyio
async def test_read_only_server_registers_only_read_tools(afas: FakeAfasApi) -> None:
    """Without AFAS_ALLOW_WRITES no tool can change data, and every tool says so in its annotations."""
    async with Client(server_for(afas)) as client:
        tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == READ_TOOLS
    assert all(tool.annotations is not None and tool.annotations.read_only_hint for tool in tools)


@pytest.mark.anyio
async def test_writes_enabled_adds_write_tools_with_honest_annotations(afas: FakeAfasApi) -> None:
    """With writes enabled the three write tools appear, marked as not read-only."""
    async with Client(server_for(afas, allow_writes=True)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == READ_TOOLS | WRITE_TOOLS
    assert tools['afas_insert'].annotations is not None
    assert tools['afas_insert'].annotations.read_only_hint is False
    assert tools['afas_insert'].annotations.destructive_hint is False
    assert tools['afas_update'].annotations is not None
    assert tools['afas_update'].annotations.destructive_hint is True
    assert tools['afas_delete'].annotations is not None
    assert tools['afas_delete'].annotations.destructive_hint is True


@pytest.mark.anyio
async def test_tool_schemas_describe_parameters(afas: FakeAfasApi) -> None:
    """Parameter descriptions reach the model through the input schema."""
    async with Client(server_for(afas)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    properties = tools['afas_get_rows'].input_schema['properties']
    assert 'connector_id' in tools['afas_get_rows'].input_schema['required']
    assert 'ctx' not in properties
    assert 'paging' in properties['order_by']['description']
    assert tools['afas_get_rows'].description is not None
    assert 'GetConnector' in tools['afas_get_rows'].description


@pytest.mark.anyio
async def test_connection_info(afas: FakeAfasApi) -> None:
    """The info tool reports the environment and proves the token works."""
    async with Client(server_for(afas)) as client:
        result = await client.call_tool('afas_connection_info', {})
    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content['base_url'] == 'https://12345.rest.afas.online/profitrestservices'
    assert result.structured_content['profit_version'] == {'version': '2026.1'}
    assert result.structured_content['writes_enabled'] is False


@pytest.mark.anyio
async def test_list_connectors_filters_by_kind_and_search(afas: FakeAfasApi) -> None:
    """Search narrows by keyword; kind hides the other family."""
    async with Client(server_for(afas)) as client:
        everything = await client.call_tool('afas_list_connectors', {})
        searched = await client.call_tool('afas_list_connectors', {'search': 'medew'})
        updates = await client.call_tool('afas_list_connectors', {'kind': 'update'})
    assert everything.structured_content is not None
    assert everything.structured_content['get_connector_count'] == 2
    assert everything.structured_content['update_connector_count'] == 1
    assert searched.structured_content is not None
    assert [item['id'] for item in searched.structured_content['get_connectors']] == ['Profit_Employees']
    assert updates.structured_content is not None
    assert not updates.structured_content['get_connectors']
    assert [item['id'] for item in updates.structured_content['update_connectors']] == ['KnSubject']


@pytest.mark.anyio
async def test_describe_connectors(afas: FakeAfasApi) -> None:
    """Both describe tools pass the AFAS metainfo through untouched."""
    async with Client(server_for(afas)) as client:
        get_info = await client.call_tool('afas_describe_get_connector', {'connector_id': 'Profit_Employees'})
        update_info = await client.call_tool('afas_describe_update_connector', {'connector_id': 'KnSubject'})
    assert get_info.structured_content == EMPLOYEE_FIELDS
    assert update_info.structured_content == UPDATE_SCHEMA


@pytest.mark.anyio
async def test_get_rows_pages_and_passes_filters(afas: FakeAfasApi) -> None:
    """Paging metadata tells the model whether to fetch more; filters reach AFAS as query parameters."""
    arguments = {
        'connector_id': 'Profit_Employees',
        'take': 2,
        'filters': [{'field': 'Name', 'operator': 'contains', 'value': 'a'}],
        'order_by': ['Id'],
    }
    async with Client(server_for(afas)) as client:
        first = await client.call_tool('afas_get_rows', arguments)
        second = await client.call_tool('afas_get_rows', {**arguments, 'skip': 2})
    assert first.structured_content is not None
    assert first.structured_content['rows'] == EMPLOYEES[:2]
    assert first.structured_content['has_more'] is True
    assert first.structured_content['next_skip'] == 2
    assert second.structured_content is not None
    assert second.structured_content['rows'] == EMPLOYEES[2:]
    assert second.structured_content['has_more'] is False
    assert second.structured_content['next_skip'] is None
    params = dict(afas.calls('GET')[-1].url.params)
    assert params['filterfieldids'] == 'Name'
    assert params['filtervalues'] == '%a%'
    assert params['operatortypes'] == '6'
    assert params['orderbyfieldids'] == 'Id'


@pytest.mark.anyio
async def test_get_rows_uses_default_take(afas: FakeAfasApi) -> None:
    """Without take the configured default page size applies."""
    async with Client(server_for(afas, default_take=2)) as client:
        result = await client.call_tool('afas_get_rows', {'connector_id': 'Profit_Employees'})
    assert result.structured_content is not None
    assert result.structured_content['take'] == 2
    assert result.structured_content['row_count'] == 2


@pytest.mark.anyio
async def test_get_rows_rejects_bad_paging(afas: FakeAfasApi) -> None:
    """Out-of-range paging is refused before AFAS is called, with the limit in the message."""
    async with Client(server_for(afas, max_take=50)) as client:
        too_many = await client.call_tool('afas_get_rows', {'connector_id': 'Profit_Employees', 'take': 51})
        negative = await client.call_tool('afas_get_rows', {'connector_id': 'Profit_Employees', 'skip': -1})
    assert too_many.is_error is True
    assert 'between 1 and 50' in error_text(too_many)
    assert negative.is_error is True
    assert not afas.calls('GET')


@pytest.mark.anyio
async def test_afas_errors_become_tool_errors(afas: FakeAfasApi) -> None:
    """AFAS refusals are reported to the model as tool errors with the AFAS message, not as crashes."""
    async with Client(server_for(afas)) as client:
        result = await client.call_tool('afas_describe_get_connector', {'connector_id': 'Nope'})
    assert result.is_error is True
    assert 'HTTP 404: Onbekende connector' in error_text(result)
    assert '(no such id)' in error_text(result)


@pytest.mark.anyio
async def test_validate_payload_reports_issues_and_body(afas: FakeAfasApi) -> None:
    """The dry-run tool works in read-only mode and shows the body that would be sent."""
    async with Client(server_for(afas)) as client:
        result = await client.call_tool(
            'afas_validate_payload',
            {'connector_id': 'KnSubject', 'element': {'Fields': {'Ds': 'x', 'Bogus': 1}}},
        )
    assert result.structured_content is not None
    assert result.structured_content['valid'] is False
    assert [issue['path'] for issue in result.structured_content['issues']] == ['Fields.Bogus', 'Fields.StId']
    assert result.structured_content['body'] == {'KnSubject': {'Element': {'Fields': {'Ds': 'x', 'Bogus': 1}}}}


@pytest.mark.anyio
async def test_write_tools_are_unknown_when_disabled(afas: FakeAfasApi) -> None:
    """A read-only server does not merely refuse writes, it does not have the tools."""
    async with Client(server_for(afas)) as client:
        result = await client.call_tool('afas_insert', {'connector_id': 'KnSubject', 'element': {}})
    assert result.is_error is True
    assert 'Unknown tool' in error_text(result)
    assert not afas.calls('POST')


@pytest.mark.anyio
async def test_insert_validates_before_sending(afas: FakeAfasApi) -> None:
    """An invalid payload never reaches AFAS; a valid one does and the new key comes back."""
    async with Client(server_for(afas, allow_writes=True)) as client:
        rejected = await client.call_tool(
            'afas_insert', {'connector_id': 'KnSubject', 'element': {'Fields': {'Ds': 'x'}}}
        )
        assert rejected.is_error is True
        assert 'Fields.StId: mandatory field is missing' in error_text(rejected)
        assert not afas.calls('POST')
        accepted = await client.call_tool(
            'afas_insert', {'connector_id': 'KnSubject', 'element': {'Fields': {'StId': 1, 'Ds': 'x'}}}
        )
    assert accepted.structured_content == {
        'connector_id': 'KnSubject',
        'operation': 'insert',
        'result': {'results': {'KnSubject': {'SbId': 42}}},
    }
    assert len(afas.calls('POST')) == 1


@pytest.mark.anyio
async def test_insert_can_skip_validation(afas: FakeAfasApi) -> None:
    """Validation is a safety net the caller may switch off for connectors whose schema is incomplete."""
    async with Client(server_for(afas, allow_writes=True)) as client:
        result = await client.call_tool(
            'afas_insert', {'connector_id': 'KnSubject', 'element': {'Fields': {'Ds': 'x'}}, 'validate': False}
        )
    assert result.is_error is False
    assert len(afas.calls('POST')) == 1


@pytest.mark.anyio
async def test_update_can_skip_validation(afas: FakeAfasApi) -> None:
    """Like insert, update sends an unvalidated payload when asked to."""
    async with Client(server_for(afas, allow_writes=True)) as client:
        result = await client.call_tool(
            'afas_update', {'connector_id': 'KnSubject', 'element': {'Fields': {'Bogus': 1}}, 'validate': False}
        )
    assert result.is_error is False
    assert len(afas.calls('PUT')) == 1


@pytest.mark.anyio
async def test_update_and_delete(afas: FakeAfasApi) -> None:
    """Updates PUT the element with its key; deletes hit the documented path."""
    async with Client(server_for(afas, allow_writes=True)) as client:
        updated = await client.call_tool(
            'afas_update', {'connector_id': 'KnSubject', 'element': {'@SbId': 42, 'Fields': {'Ds': 'y'}}}
        )
        deleted = await client.call_tool(
            'afas_delete', {'connector_id': 'KnSubject', 'key_field': 'SbId', 'key_value': 42}
        )
    assert updated.structured_content == {'connector_id': 'KnSubject', 'operation': 'update', 'result': None}
    assert deleted.structured_content == {
        'connector_id': 'KnSubject',
        'operation': 'delete',
        'key_field': 'SbId',
        'key_value': 42,
        'result': None,
    }
    assert afas.calls('PUT')[0].url.path == '/profitrestservices/connectors/KnSubject'
    assert afas.calls('DELETE')[0].url.path == '/profitrestservices/connectors/KnSubject/KnSubject/@SbId/42'
