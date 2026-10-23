# Review rules

What the review lanes hold a PR in this repo to. AGENTS.md has the house rules; this file says what is worth raising.

## Important (blocker or major)
- A write tool (insert, update, delete) registered without `AFAS_ALLOW_WRITES=true`, writes that skip validation by default, or a weakened `afas_validate_payload`.
- An AFAS token, member id or `.env` value anywhere in code, tests, docs, logs or the diff (tests use the fictional token in `tests/conftest.py`).
- A new dependency that is not MIT, BSD, Apache, PSF or ISC licensed, or that is unlicensed or copyleft.
- Changed behaviour without a matching update to `docs/reference/tools.md` or `docs/reference/configuration.md`.
- New behaviour without tests that drive the server through the in-process MCP client against the fake AFAS (`tests/test_server.py`), or any drop in the 100% coverage ratchet.
- A bundled connector catalogue or field list (the server discovers them from AFAS metainfo), a new tool, transport or per-user AFAS identity nobody asked for.
- A hand edit to one of the five uv pins (use `./workflow.cmd develop.bump-uv`), or a `.security-overrides` entry without justification or expiry.
- A commit or PR title that is not Conventional Commits (`cz check` runs in `lint`; the changelog is generated from them).
- A claim of AFAS behaviour that CI cannot verify, without the PR saying so.

## Minor
- `TYPE_CHECKING` blocks, `from __future__ import annotations`, or syntax newer than Python 3.10.
- A public item without a Google docstring, a logger not named per class, or a module-level function with a leading underscore.
- A function that mutates its arguments instead of returning a value.
- A PR that bundles more than one logical change.

## Skip
- Style, import order and formatting that `ruff` owns (single quotes, 120 columns).
- Findings from pylint, ty or complexipy that `./workflow.cmd lint` already reports.
- Dependabot bumps and lockfile churn.
- More than three nits per lane.
