"""Tests for rewriting the uv pins in pyproject.toml (`_CI/uv_release.py`)."""

import pytest

from _CI.uv_release import UvReleaseError, current_pin, rewrite_pins

PYPROJECT = """\
[dependency-groups]
test = [
    "pytest==9.1.1",
    "uv==0.13.4",
]

[build-system]
requires = ["uv_build>=0.8.15,<=0.13.4"]

[tool.uv]
required-version = ">=0.13.4"

[tool.image]
base-image = "ghcr.io/astral-sh/uv:0.13.4-python3.10-trixie-slim@sha256:0123456789abcdef"
"""


def test_current_pin_reads_the_version_from_the_floor() -> None:
    """The bump starts from the version in the `>=` floor, not from any other pin."""
    assert current_pin(PYPROJECT) == '0.13.4'


@pytest.mark.parametrize(
    'pyproject',
    [
        pytest.param(PYPROJECT.replace('>=0.13.4', '==0.13.4'), id='legacy-exact-pin'),
        pytest.param(PYPROJECT.replace('required-version', 'other-key'), id='missing-key'),
    ],
)
def test_current_pin_refuses_anything_but_a_floor(pyproject: str) -> None:
    """A legacy exact pin or a missing key raises instead of guessing a version to bump from."""
    with pytest.raises(UvReleaseError, match='required-version floor'):
        current_pin(pyproject)


def test_rewrite_pins_moves_every_pin_to_the_new_version() -> None:
    """Every uv pin moves together, and the digest is set alongside the tag."""
    updated = rewrite_pins(PYPROJECT, '0.13.5', 'sha256:fedcba9876543210', '3.11')

    assert '"uv==0.13.5",' in updated
    assert 'requires = ["uv_build>=0.8.15,<=0.13.5"]' in updated
    assert 'required-version = ">=0.13.5"' in updated
    assert 'base-image = "ghcr.io/astral-sh/uv:0.13.5-python3.11-trixie-slim@sha256:fedcba9876543210"' in updated
    assert '0.13.4' not in updated


def test_rewrite_pins_rebuilds_the_tag_from_the_python_version() -> None:
    """A raised Python floor replaces the old `-pythonX.Y` suffix instead of keeping it."""
    updated = rewrite_pins(PYPROJECT, '0.13.5', 'sha256:fedcba9876543210', '3.12')

    assert 'uv:0.13.5-python3.12-trixie-slim@sha256:fedcba9876543210"' in updated
    assert 'python3.10' not in updated


def test_rewrite_pins_refuses_a_half_bumped_file() -> None:
    """A missing pin raises instead of writing a pyproject that disagrees with itself."""
    without_base_image = PYPROJECT.replace('base-image', 'other')

    with pytest.raises(UvReleaseError, match='base-image reference'):
        rewrite_pins(without_base_image, '0.13.5', 'sha256:fedcba9876543210', '3.11')
