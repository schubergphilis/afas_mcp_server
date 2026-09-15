"""Tests for the command line entry point."""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from afas_mcp_server import __main__ as cli
from afas_mcp_server.client import AfasClient
from afas_mcp_server.configuration import Settings


class RecordingServer:
    """Stands in for the MCP server so the CLI can be exercised without opening stdio."""

    def __init__(self) -> None:
        """Start with nothing recorded."""
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, transport: str, **kwargs: Any) -> None:  # noqa: ANN401
        """Record how the server was asked to run."""
        self.calls.append((transport, kwargs))


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the CLI at a fictional environment, from a directory without a .env file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('AFAS_MEMBER_ID', '12345')
    monkeypatch.setenv('AFAS_TOKEN', 'ABC123')


def fake_client(handler: httpx2.MockTransport) -> type[AfasClient]:
    """A client class that talks to ``handler`` instead of AFAS Online."""

    class FakeClient(AfasClient):
        """The real client, pinned to the fake transport whatever the CLI passes."""

        def __init__(self, settings: Settings, transport: object = None) -> None:  # noqa: ARG002
            super().__init__(settings, transport=handler)

    return FakeClient


def test_parser_defaults() -> None:
    """Out of the box the server speaks stdio, which is what desktop MCP clients expect."""
    args = cli.build_parser().parse_args([])
    assert args.transport == 'stdio'
    assert args.check is False
    assert (args.host, args.port, args.path) == ('127.0.0.1', 8000, '/mcp')


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """--version prints the installed version and exits cleanly."""
    with pytest.raises(SystemExit) as exit_info:
        cli.main(['--version'])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith('afas-mcp-server ')


def test_missing_configuration_explains_and_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing token is a configuration error, reported on stderr with a pointer to .env.example."""
    monkeypatch.chdir(tmp_path)
    assert cli.main([]) == 2
    err = capsys.readouterr().err
    assert 'Invalid AFAS configuration' in err
    assert 'token' in err
    assert '.env.example' in err


@pytest.mark.usefixtures('configured')
def test_check_prints_report(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """--check proves the token works and prints where the server would connect to."""
    transport = httpx2.MockTransport(lambda _request: httpx2.Response(200, json={'version': '2026.1'}))
    monkeypatch.setattr(cli, 'AfasClient', fake_client(transport))
    assert cli.main(['--check']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {
        'base_url': 'https://12345.rest.afas.online/profitrestservices',
        'writes_enabled': False,
        'profit_version': {'version': '2026.1'},
    }


@pytest.mark.usefixtures('configured')
def test_check_reports_afas_refusal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A rejected token exits 1 with the AFAS message on stderr."""
    transport = httpx2.MockTransport(lambda _request: httpx2.Response(401, json={'externalMessage': 'Ongeldige token'}))
    monkeypatch.setattr(cli, 'AfasClient', fake_client(transport))
    assert cli.main(['--check']) == 1
    assert 'Ongeldige token' in capsys.readouterr().err


@pytest.mark.usefixtures('configured')
def test_check_reports_network_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Connection problems are reported the same way as AFAS refusals."""

    def unreachable(_request: httpx2.Request) -> httpx2.Response:
        message = 'name resolution failed'
        raise httpx2.ConnectError(message)

    monkeypatch.setattr(cli, 'AfasClient', fake_client(httpx2.MockTransport(unreachable)))
    assert cli.main(['--check']) == 1
    assert 'name resolution failed' in capsys.readouterr().err


@pytest.mark.usefixtures('configured')
def test_serve_over_stdio_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without flags the server runs on stdio."""
    server = RecordingServer()
    monkeypatch.setattr(cli, 'build_server', lambda _settings: server)
    assert cli.main([]) == 0
    assert server.calls == [('stdio', {})]


@pytest.mark.usefixtures('configured')
def test_serve_over_streamable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP transport receives the bind address, port and path."""
    server = RecordingServer()
    monkeypatch.setattr(cli, 'build_server', lambda _settings: server)
    argv = ['--transport', 'streamable-http', '--host', '0.0.0.0', '--port', '9000', '--path', '/afas']  # noqa: S104
    assert cli.main(argv) == 0
    expected = {'host': '0.0.0.0', 'port': 9000, 'streamable_http_path': '/afas'}  # noqa: S104
    assert server.calls == [('streamable-http', expected)]
