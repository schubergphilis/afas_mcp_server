"""Runtime configuration for the AFAS MCP server, read from ``AFAS_*`` environment variables."""

import base64
import binascii
from enum import Enum
from typing import Annotated

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

XML_ENVELOPE_PREFIX = '<token'
XML_ENVELOPE_TEMPLATE = '<token><version>1</version><data>{data}</data></token>'
AFAS_ONLINE_DOMAIN = 'afas.online'
REST_SERVICES_PATH = 'profitrestservices'
LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')


class Environment(str, Enum):
    """The kind of AFAS Online environment, which selects the REST hostname."""

    PRODUCTION = 'production'
    TEST = 'test'
    ACCEPT = 'accept'

    @property
    def host_prefix(self) -> str:
        """The hostname fragment AFAS Online uses for this environment kind."""
        return HOST_PREFIXES[self]


HOST_PREFIXES = {
    Environment.PRODUCTION: 'rest',
    Environment.TEST: 'resttest',
    Environment.ACCEPT: 'restaccept',
}


def is_encoded_token(candidate: str) -> bool:
    """Return whether ``candidate`` is already the base64 form of a ``<token>`` XML document.

    Args:
        candidate: The text to inspect.

    Returns:
        True when the text base64-decodes to something that starts with ``<token``.
    """
    try:
        decoded = base64.b64decode(candidate, validate=True)
    except (binascii.Error, ValueError):
        return False
    return decoded.lstrip().startswith(XML_ENVELOPE_PREFIX.encode('ascii'))


def encode_token(token: str) -> str:
    """Return the base64 token AFAS expects after ``AfasToken`` in the ``Authorization`` header.

    Accepts the token in any of the forms AFAS hands out: the full ``<token>`` XML, only the value of its
    ``<data>`` element, or the XML already base64 encoded.

    Args:
        token: The app connector token in one of the accepted forms.

    Returns:
        The base64 encoded ``<token>`` XML.
    """
    candidate = token.strip()
    if candidate.startswith(XML_ENVELOPE_PREFIX):
        xml = candidate
    elif is_encoded_token(candidate):
        return candidate
    else:
        xml = XML_ENVELOPE_TEMPLATE.format(data=candidate)
    return base64.b64encode(xml.encode('utf-8')).decode('ascii')


class Settings(BaseSettings):
    """Connection and behaviour settings, populated from ``AFAS_*`` environment variables or a ``.env`` file.

    Either ``member_id`` (optionally with ``environment``) or an explicit ``base_url`` must be provided.
    """

    model_config = SettingsConfigDict(env_prefix='AFAS_', env_file='.env', env_file_encoding='utf-8', extra='ignore')

    token: Annotated[
        SecretStr,
        Field(description='App connector token: the <token> XML, only its <data> value, or the base64 encoded XML.'),
    ]
    member_id: Annotated[str | None, Field(description='AFAS Online environment number, e.g. 12345.')] = None
    environment: Annotated[Environment, Field(description='production, test or accept.')] = Environment.PRODUCTION
    base_url: Annotated[
        str | None,
        Field(description='Full REST base URL; overrides member_id and environment.'),
    ] = None
    allow_writes: Annotated[bool, Field(description='Register the insert, update and delete tools.')] = False
    timeout_seconds: Annotated[float, Field(gt=0, description='HTTP timeout per AFAS call, in seconds.')] = 60.0
    default_take: Annotated[int, Field(ge=1, description='Rows per page when a tool call gives no take.')] = 100
    max_take: Annotated[int, Field(ge=1, description='Largest page size a tool call may request.')] = 1000
    language: Annotated[
        str,
        Field(description='Accept-Language for AFAS messages: nl-nl, nl-be, fr-fr, de-de or en-us.'),
    ] = 'nl-nl'
    log_level: Annotated[str, Field(description='Python log level for the server process.')] = 'INFO'

    @model_validator(mode='after')
    def check_consistency(self) -> Self:
        """Reject settings that cannot produce a base URL or a usable log level.

        Returns:
            The validated settings, unchanged.

        Raises:
            ValueError: When neither an endpoint nor a known log level is available.
        """
        if not self.base_url and not (self.member_id or '').strip():
            message = 'set AFAS_MEMBER_ID (optionally with AFAS_ENVIRONMENT) or AFAS_BASE_URL'
            raise ValueError(message)
        if self.python_log_level not in LOG_LEVELS:
            message = f'AFAS_LOG_LEVEL must be one of {", ".join(LOG_LEVELS)}, not {self.log_level!r}'
            raise ValueError(message)
        return self

    @property
    def python_log_level(self) -> str:
        """The log level as Python's ``logging`` module spells it."""
        return self.log_level.strip().upper()

    @property
    def rest_base_url(self) -> str:
        """The REST services base URL, without a trailing slash."""
        if self.base_url:
            return self.base_url.rstrip('/')
        member = (self.member_id or '').strip()
        return f'https://{member}.{self.environment.host_prefix}.{AFAS_ONLINE_DOMAIN}/{REST_SERVICES_PATH}'

    @property
    def authorization_header(self) -> str:
        """The value of the ``Authorization`` header sent with every AFAS call."""
        return f'AfasToken {encode_token(self.token.get_secret_value())}'
