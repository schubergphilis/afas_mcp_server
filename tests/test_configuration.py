"""Tests for settings and token handling."""

import pytest
from pydantic import ValidationError

from afas_mcp_server.configuration import Environment, Settings, encode_token, is_encoded_token
from tests.conftest import ENCODED_TOKEN, RAW_TOKEN, make_settings


def test_encode_token_accepts_xml() -> None:
    """The full <token> XML is base64 encoded as-is."""
    assert encode_token(RAW_TOKEN) == ENCODED_TOKEN


def test_encode_token_accepts_data_only() -> None:
    """Only the <data> value is wrapped in the XML envelope before encoding."""
    assert encode_token('ABC123') == ENCODED_TOKEN


def test_encode_token_passes_encoded_through() -> None:
    """An already encoded token is returned unchanged."""
    assert encode_token(ENCODED_TOKEN) == ENCODED_TOKEN


def test_encode_token_strips_whitespace() -> None:
    """Surrounding whitespace from copy-pasting is ignored."""
    assert encode_token(f'  {RAW_TOKEN}\n') == ENCODED_TOKEN


def test_hex_data_token_is_not_mistaken_for_base64() -> None:
    """A hexadecimal data token decodes as base64 but is not a <token> document."""
    assert not is_encoded_token('ABCDEF0123456789ABCDEF0123456789')


@pytest.mark.parametrize(
    ('environment', 'expected'),
    [
        (Environment.PRODUCTION, 'https://12345.rest.afas.online/profitrestservices'),
        (Environment.TEST, 'https://12345.resttest.afas.online/profitrestservices'),
        (Environment.ACCEPT, 'https://12345.restaccept.afas.online/profitrestservices'),
    ],
)
def test_rest_base_url_per_environment(environment: Environment, expected: str) -> None:
    """The environment kind selects the AFAS Online hostname."""
    assert make_settings(environment=environment).rest_base_url == expected


def test_environment_accepts_its_string_value() -> None:
    """Environment variables arrive as strings and are mapped onto the enum."""
    assert make_settings(environment='test').environment is Environment.TEST


def test_base_url_override_wins_and_loses_trailing_slash() -> None:
    """An explicit base URL replaces the derived one, without a trailing slash."""
    settings = make_settings(member_id=None, base_url='https://afas.example.test/ProfitRestServices/')
    assert settings.rest_base_url == 'https://afas.example.test/ProfitRestServices'


def test_member_id_or_base_url_is_required() -> None:
    """Without either there is no endpoint to call."""
    with pytest.raises(ValidationError, match='AFAS_MEMBER_ID'):
        make_settings(member_id='  ')


def test_token_is_required() -> None:
    """A token is the one setting without a default."""
    with pytest.raises(ValidationError, match='token'):
        Settings(_env_file=None, member_id='12345')


def test_authorization_header() -> None:
    """The header carries the AfasToken scheme and the encoded token."""
    assert make_settings().authorization_header == f'AfasToken {ENCODED_TOKEN}'


def test_log_level_is_case_insensitive() -> None:
    """Lower-case levels are accepted and normalised."""
    assert make_settings(log_level='debug').python_log_level == 'DEBUG'


def test_unknown_log_level_is_rejected() -> None:
    """A typo in the level fails fast instead of at the first log call."""
    with pytest.raises(ValidationError, match='AFAS_LOG_LEVEL'):
        make_settings(log_level='loud')


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every setting is read from an AFAS_ prefixed environment variable."""
    monkeypatch.setenv('AFAS_MEMBER_ID', '99999')
    monkeypatch.setenv('AFAS_TOKEN', 'ABC123')
    monkeypatch.setenv('AFAS_ENVIRONMENT', 'accept')
    monkeypatch.setenv('AFAS_ALLOW_WRITES', 'true')
    monkeypatch.setenv('AFAS_MAX_TAKE', '250')
    settings = Settings(_env_file=None)
    assert settings.rest_base_url == 'https://99999.restaccept.afas.online/profitrestservices'
    assert settings.allow_writes is True
    assert settings.max_take == 250
    assert settings.token.get_secret_value() == 'ABC123'


def test_secret_token_does_not_leak_in_repr() -> None:
    """The token must not show up when settings are printed or logged."""
    assert 'ABC123' not in repr(make_settings())
