"""Security task definitions."""

import os
import re
from datetime import date
from typing import NamedTuple, cast

from invoke import Collection, Context, Task, task

from .configuration import IGNORE_PATTERN, SBOM_FILE, SECURITY_OVERRIDE_ENV, SECURITY_OVERRIDES_FILE
from .sbom import render_sbom, validate_sbom, write_sbom
from .shared import execute, logged


class Suppression(NamedTuple):
    """A validated suppression: which vulnerability, until when, and where it came from."""

    vulnerability_id: str
    expires: date | None
    source: str


def validate_override_entry(entry: str, source: str, *, require_expiry: bool = False) -> None:
    """Abort with a clear message if `entry` is not a valid suppression.

    Format: ``<VULN_ID>[::YYYY-MM-DD]`` — the vulnerability id must match the
    project-wide ``IGNORE_PATTERN``, and the expiry, when present, must be a
    real calendar date. ``source`` is prepended to the error for context
    (e.g. ``.security-overrides:7``).

    With ``require_expiry``, a missing expiry is also an error. That is applied to
    suppressions arriving from outside the repository, where a permanent entry would
    leave no reviewable trace.

    Raises:
        SystemExit: with exit code 1 if the entry is malformed.
    """
    expected = (
        '<VULN_ID>[::YYYY-MM-DD] — e.g. CVE-2024-1234::2026-12-31 (expires, '
        'forces re-review on the date) or plain CVE-2024-1234 (permanent '
        'suppression, the audit will never flag this vulnerability again — '
        'prefer an expiry when you can)'
    )
    match = IGNORE_PATTERN.fullmatch(entry)
    if not match:
        print(f'{source}: invalid entry {entry!r}; expected {expected}')
        raise SystemExit(1)
    expiry = match.group('expiration_date')
    if not expiry:
        if require_expiry:
            print(
                f'{source}: {entry!r} has no expiry. Suppressions from this source must expire '
                f'(<VULN_ID>::YYYY-MM-DD) — a permanent one here would mute a finding with no '
                f'record in the repository. Put permanent suppressions in {SECURITY_OVERRIDES_FILE}, '
                f'where they are reviewed with the code.'
            )
            raise SystemExit(1)
        return
    try:
        date.fromisoformat(expiry)
    except ValueError as exc:
        print(f'{source}: invalid expiry {expiry!r}: {exc}; expected YYYY-MM-DD (or omit for a permanent suppression)')
        raise SystemExit(1) from None


def parse_suppressions(raw: str, source: str, *, require_expiry: bool = False) -> list[Suppression]:
    """Validate every entry in a comma/whitespace-separated list and return them parsed.

    Each entry is matched whole. Scanning the joined list for id-shaped substrings
    instead would let malformed input through in the most dangerous direction: a
    mistyped expiry such as ``CVE-1::2020-1-1`` does not match the optional expiry
    group, so the id alone would match and the entry would silently become a
    *permanent* suppression, with the date fragments tacked on as extra ids.
    """
    suppressions: list[Suppression] = []
    for entry in (part for part in re.split(r'[,\s]+', raw.strip()) if part):
        validate_override_entry(entry, source, require_expiry=require_expiry)
        match = cast(re.Match[str], IGNORE_PATTERN.fullmatch(entry))
        expiry = match.group('expiration_date')
        suppressions.append(
            Suppression(
                vulnerability_id=match.group('vulnerability_id'),
                expires=date.fromisoformat(expiry) if expiry else None,
                source=source,
            )
        )
    return suppressions


def load_overrides_file() -> list[Suppression]:
    """Return validated suppressions from `.security-overrides`, stripping `#` comments and blanks."""
    if not SECURITY_OVERRIDES_FILE.exists():
        return []
    suppressions: list[Suppression] = []
    for lineno, raw in enumerate(SECURITY_OVERRIDES_FILE.read_text(encoding='utf-8').splitlines(), start=1):
        entry = raw.split('#', 1)[0].strip()
        if not entry:
            continue
        suppressions.extend(parse_suppressions(entry, f'{SECURITY_OVERRIDES_FILE}:{lineno}'))
    return suppressions


@task
@logged('secure.audit')
def audit(context: Context, ignore: str | None = None) -> None:
    """Run pip-audit security scan.

    Suppressions are sourced, in precedence order, from ``--ignore``, the
    ``AFAS_MCP_SERVER_SECURITY_OVERRIDE`` environment
    variable, and a ``.security-overrides`` file at the project root. All three
    are merged and deduplicated. Each entry is a vulnerability ID with an
    optional expiry (``CVE-2024-1234::2026-12-31``); entries whose expiry has
    passed are dropped so the audit fails until the suppression is reviewed.

    Every entry is validated whatever its source, and the two sources that leave no
    trace in the repository — ``--ignore`` and the environment variable — must carry an
    expiry, so they cannot mute a finding indefinitely. Whatever ends up applied is
    printed with its origin, so a suppression injected through CI configuration alone
    still shows up in the build log.

    Args:
        context: Invoke context.
        ignore: Comma-separated vulnerability IDs to ignore.
    """
    today = date.today()  # noqa: DTZ011
    suppressions = [
        *parse_suppressions(ignore or '', '--ignore', require_expiry=True),
        *parse_suppressions(
            os.environ.get(SECURITY_OVERRIDE_ENV, ''), f'${SECURITY_OVERRIDE_ENV}', require_expiry=True
        ),
        *load_overrides_file(),
    ]
    active: dict[str, Suppression] = {}
    for suppression in suppressions:
        if suppression.expires is not None and suppression.expires <= today:
            print(
                f'{suppression.source}: suppression for {suppression.vulnerability_id} expired on '
                f'{suppression.expires}; it will be reported again until re-reviewed.'
            )
            continue
        # First wins, which is the documented precedence: --ignore, then env, then file.
        active.setdefault(suppression.vulnerability_id, suppression)
    if active:
        print(f'Applying {len(active)} suppression(s):')
        for suppression in active.values():
            expiry = f'expires {suppression.expires}' if suppression.expires else 'permanent'
            print(f'  {suppression.vulnerability_id} ({expiry}) from {suppression.source}')
    ignore_args = ' '.join(f'--ignore-vuln {vulnerability_id}' for vulnerability_id in active)
    ignore_opts = f' {ignore_args}' if ignore_args else ''
    execute(context, f'uv run pip-audit{ignore_opts}')


@task
@logged('secure.sbom-extract')
def sbom_extract(context: Context, write: bool = False) -> None:  # noqa: ARG001
    """Compose a CycloneDX SBOM covering runtime deps, vendored CI deps, and pipeline components.

    By default prints the SBOM to stdout. With --write, writes the SBOM to the
    package data path so `uv build` ships it inside the wheel.

    Args:
        context: Invoke context.
        write: Write SBOM to ``src/<package>/sbom.cdx.json`` instead of printing to stdout.
    """
    if write:
        write_sbom()
        print(f'Wrote SBOM to {SBOM_FILE}.')
    else:
        print(render_sbom())


@task
@logged('secure.sbom-validate')
def sbom_validate(context: Context) -> None:
    """Validate the generated SBOM against the CycloneDX 1.7 JSON schema.

    Re-runs ``sbom-extract --write`` if the SBOM file is missing so the
    validation has something to check.
    """
    if not SBOM_FILE.exists():
        sbom_extract(context, write=True)
    errors = validate_sbom()
    if errors:
        for err in errors:
            print(err)
        raise SystemExit(1)
    print(f'SBOM at {SBOM_FILE} validates against CycloneDX 1.7 schema.')


@task
@logged('secure.validate-overrides')
def validate_overrides(context: Context) -> None:  # noqa: ARG001
    """Validate every entry in .security-overrides without running the audit.

    Intended as a pre-commit hook: fails fast with a ``file:line: <reason>``
    message if any entry is malformed, the expiry is not a real date, or the
    file contains merge conflict markers. Silent no-op when the file is absent.
    """
    load_overrides_file()


@task
@logged('secure')
def secure(context: Context) -> None:
    """Run all security checks; reports all failures before exiting."""
    failed = False
    try:
        audit(context)
    except SystemExit:
        failed = True
    try:
        sbom_extract(context, write=True)
    except SystemExit:
        failed = True
    try:
        sbom_validate(context)
    except SystemExit:
        failed = True
    if failed:
        raise SystemExit(1)


namespace = Collection('secure')
namespace.add_task(cast(Task, secure), default=True, name='all')
namespace.add_task(cast(Task, audit))
namespace.add_task(cast(Task, sbom_extract))
namespace.add_task(cast(Task, sbom_validate))
namespace.add_task(cast(Task, validate_overrides))
