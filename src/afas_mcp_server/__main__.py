"""Command-line entry point, installed as ``afas-mcp-server`` and reachable as ``python -m afas_mcp_server``."""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from typing import Any

import httpx2
from pydantic import ValidationError

from .client import AfasClient, AfasError
from .configuration import Settings
from .server import build_server, package_version

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8000
DEFAULT_PATH = '/mcp'
EXIT_OK = 0
EXIT_CONNECTION_FAILED = 1
EXIT_CONFIGURATION_INVALID = 2
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


def build_parser() -> argparse.ArgumentParser:
    """Describe the command line."""
    parser = argparse.ArgumentParser(
        prog='afas-mcp-server',
        description='MCP server for AFAS Profit. Connection settings come from AFAS_* environment variables or .env.',
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {package_version()}')
    parser.add_argument(
        '--transport',
        choices=('stdio', 'streamable-http'),
        default='stdio',
        help='stdio for local MCP clients (default); streamable-http to serve over HTTP.',
    )
    parser.add_argument(
        '--host', default=DEFAULT_HOST, help=f'Bind address for streamable-http (default {DEFAULT_HOST}).'
    )
    parser.add_argument(
        '--port', type=int, default=DEFAULT_PORT, help=f'Port for streamable-http (default {DEFAULT_PORT}).'
    )
    parser.add_argument('--path', default=DEFAULT_PATH, help=f'URL path for streamable-http (default {DEFAULT_PATH}).')
    parser.add_argument(
        '--check',
        action='store_true',
        help='Ask AFAS for its Profit version to verify the settings and token, print the result and exit.',
    )
    return parser


def configure_logging(level: str) -> None:
    """Log to stderr; stdout belongs to the MCP protocol when running over stdio."""
    logging.basicConfig(level=level, stream=sys.stderr, format=LOG_FORMAT)


def load_settings() -> Settings | None:
    """Read the settings, explaining on stderr what is missing when they are invalid.

    Returns:
        The settings, or None when they could not be validated.
    """
    try:
        return Settings()
    except ValidationError as error:
        problems = '; '.join(
            f'{".".join(str(part) for part in item["loc"]) or "settings"}: {item["msg"]}' for item in error.errors()
        )
        sys.stderr.write(f'Invalid AFAS configuration: {problems}\nSee .env.example for the variables to set.\n')
        return None


async def profit_version(settings: Settings) -> dict[str, Any]:
    """Ask AFAS for its version with a short-lived client."""
    async with AfasClient(settings) as client:
        return await client.profit_version()


def run_check(settings: Settings) -> int:
    """Verify the connection and report the outcome.

    Args:
        settings: The connection settings to verify.

    Returns:
        The process exit code: 0 when AFAS answered, 1 otherwise.
    """
    try:
        info = asyncio.run(profit_version(settings))
    except (AfasError, httpx2.HTTPError) as error:
        sys.stderr.write(f'AFAS connection failed: {error}\n')
        return EXIT_CONNECTION_FAILED
    report = {'base_url': settings.rest_base_url, 'writes_enabled': settings.allow_writes, 'profit_version': info}
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return EXIT_OK


def serve(settings: Settings, args: argparse.Namespace) -> None:
    """Build the server and run it on the requested transport until the client disconnects."""
    server = build_server(settings)
    if args.transport == 'stdio':
        server.run('stdio')
    else:
        server.run('streamable-http', host=args.host, port=args.port, streamable_http_path=args.path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; defaults to the process arguments.

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if settings is None:
        return EXIT_CONFIGURATION_INVALID
    configure_logging(settings.python_log_level)
    if args.check:
        return run_check(settings)
    serve(settings, args)
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
