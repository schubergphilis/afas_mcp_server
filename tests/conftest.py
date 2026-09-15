"""Shared test fixtures for afas_mcp_server."""

import base64
import os
from pathlib import Path
from typing import Any

import pytest

from afas_mcp_server.configuration import Settings

RAW_TOKEN = '<token><version>1</version><data>ABC123</data></token>'
ENCODED_TOKEN = base64.b64encode(RAW_TOKEN.encode('utf-8')).decode('ascii')

UPDATE_SCHEMA: dict[str, Any] = {
    'id': 'KnSubject',
    'description': 'Dossieritem',
    'fields': [
        {'fieldId': 'SbId', 'primaryKey': True, 'dataType': 'int', 'label': 'Id', 'mandatory': False},
        {'fieldId': 'StId', 'primaryKey': False, 'dataType': 'int', 'label': 'Type', 'mandatory': True},
        {'fieldId': 'Ds', 'dataType': 'string', 'label': 'Omschrijving', 'mandatory': True, 'length': 10},
        {'fieldId': 'Bl', 'dataType': 'boolean', 'label': 'Bijlage', 'mandatory': False},
        {'fieldId': 'Am', 'dataType': 'decimal', 'label': 'Bedrag', 'mandatory': False, 'decimals': 2},
        {
            'fieldId': 'St',
            'dataType': 'string',
            'label': 'Status',
            'mandatory': False,
            'values': [{'id': 'A', 'description': 'Actief'}, {'id': 'I', 'description': 'Inactief'}],
        },
    ],
    'objects': [
        {
            'name': 'KnSubjectLink',
            'fields': [
                {'fieldId': 'DoCRM', 'dataType': 'boolean', 'mandatory': False},
                {'fieldId': 'ToPE', 'dataType': 'boolean', 'mandatory': True},
            ],
            'objects': [],
        }
    ],
}


def make_settings(**overrides: Any) -> Settings:  # noqa: ANN401
    """Build settings for tests without reading a ``.env`` file."""
    values: dict[str, Any] = {'member_id': '12345', 'token': RAW_TOKEN}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def isolated_afas_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the AFAS_* variables a developer's shell or .env may hold, so tests only see what they set themselves."""
    for name in [key for key in os.environ if key.startswith('AFAS_')]:
        monkeypatch.delenv(name)


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only."""
    return 'asyncio'


@pytest.fixture
def settings() -> Settings:
    """Settings for a fictional production environment."""
    return make_settings()


@pytest.fixture
def update_schema() -> dict[str, Any]:
    """A small UpdateConnector schema in the shape ``metainfo/update/{id}`` returns."""
    return UPDATE_SCHEMA


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return next(parent for parent in Path(__file__).resolve().parents if (parent / '_CI').is_dir())
