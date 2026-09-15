"""afas_mcp_server: an MCP server that exposes AFAS Profit GetConnectors, UpdateConnectors and metainfo to AI agents."""

import logging

from .client import AfasApiError, AfasClient, AfasError
from .configuration import Environment, Settings
from .filters import Filter, Operator
from .server import build_server, package_version
from .validation import Issue, validate_element

LOGGER = logging.getLogger('afas_mcp_server')
LOGGER.addHandler(logging.NullHandler())

__version__ = package_version()

__all__ = [
    'AfasApiError',
    'AfasClient',
    'AfasError',
    'Environment',
    'Filter',
    'Issue',
    'Operator',
    'Settings',
    '__version__',
    'build_server',
    'validate_element',
]
