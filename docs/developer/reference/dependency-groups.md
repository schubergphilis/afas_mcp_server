# Dependency groups

The template uses [PEP 735 dependency groups](https://peps.python.org/pep-0735/) (uv's first-class support for them) to separate dev-time tooling from runtime requirements. Each group corresponds to one workflow task family.

## Runtime

The `[project.dependencies]` list in `pyproject.toml`. These ship in the published wheel. Add via:

```bash
uv add <package>
```

## Dev-time groups

Listed under `[dependency-groups]` in `pyproject.toml`. They're installed by `develop.bootstrap` and on demand by individual workflow tasks, but never end up in the wheel.

| Group | Packages | Used by |
| --- | --- | --- |
| `dev` | Aggregator that pulls in every group below. | Default `uv sync` target; convenient for IDE setup. |
| `develop` | `pre-commit`, `commitizen`, `tomlkit` | `./workflow.cmd develop.*`, `release.*` (commitizen). |
| `lint` | `ruff`, `pylint`, `ty`, `complexipy` | `./workflow.cmd lint` and `format`. |
| `test` | `pytest`, `pytest-cov`, `pytest-xdist`, `pytest-env`, `pytest-metadata`, `pytest-html`, `coverage`, `tox`, `tox-uv` | `./workflow.cmd test`. |
| `document` | `properdocs`, `mkdocstrings[python]`, `mkdocs-include-markdown-plugin` | `./workflow.cmd document`. |
| `quality` | `pyscn` | `./workflow.cmd quality`. |
| `security` | `pip-audit`, `cyclonedx-py` | `./workflow.cmd secure`. |

## Adding to a group

```bash
uv add --group <group-name> <package>
```

This updates both `pyproject.toml` and `uv.lock`. Commit both. See [How-to: add a dependency](../how-to/add-a-dependency.md) for the full flow.

## Why everything is pinned, and what bounds the rest

Every entry in every group is pinned to an exact version, and `uv.lock` records the whole
transitive closure. CI installs from the lock, so a resolution only changes when a commit
changes it.

**This project departs from the template here.** The template also stamps a fixed
`[tool.uv] exclude-newer` date that makes uv refuse anything published later, and expects
upgrades to happen by moving that date and re-resolving by hand. This repository is instead
maintained by Dependabot and an agent (see [`AGENTS.md`](https://github.com/schubergphilis/afas_mcp_server/blob/main/AGENTS.md)), and a fixed
date would make every Dependabot lock update fail rather than wait. The seven-day cooldown
the date provided lives in `.github/dependabot.yml` (`cooldown: default-days: 7`), which
gates what is *proposed*: a release has to have been public for a week before Dependabot
opens a PR for it.

So upgrades still happen deliberately, one PR at a time:

- Dependabot opens PRs every Monday: one grouped PR for development tooling, one per runtime
  dependency. Non-major tooling and GitHub Actions updates merge automatically when CI is
  green; the rest is labelled `agent-review` and reviewed.
- Transitive dependencies are refreshed monthly with `uv lock --upgrade` in a PR titled
  `build(deps): refresh lockfile`.
- Dependabot never touches `uv` itself (see below) and, for now, ignores `ruff >= 0.16`; both
  exceptions are documented in `.github/dependabot.yml`.

`[tool.docker-versions]` is pinned by tag *and* digest. When bumping uv, change the version
in the tag and the digest together: a reference carrying both resolves to the digest, so a
bumped tag with a stale digest silently keeps the old image.

## The uv pin, and the one command that moves it

uv gets its own treatment because `[tool.uv] required-version` is an **exact** match: a stale
uv pin does not merely lag, it refuses to run. And the version appears in five places that
must agree:

| Where | Why |
|---|---|
| `[tool.uv] required-version` | the constraint every `uv` invocation checks |
| `uv==` in the `test` group | tox-uv installs a uv binary into `.venv/bin` that would otherwise shadow the image's |
| `uv_build` upper bound in `[build-system]` | the build backend ships in lockstep with uv |
| the `base-image` tag in `[tool.docker-versions]` | CI runs inside that image |
| `uv.lock` | resolved from the `test` group entry |

Like the quarantine date, **the pin was the newest release that had been public for a week
when this project was generated** — not a literal inherited from the template, which would
have grown staler the longer the template went unbumped.

It does not advance on its own. This moves all five together, re-resolving the image digest
and the lockfile in one step:

```bash
./workflow.cmd develop.bump-uv
```

It picks the newest release at least **7 days** old — long enough that a same-day release
withdrawn hours later never reaches you, and the reason the pin is always resolvable under an
`exclude-newer` stamped at generation. It refuses a version the `uv-build` backend has not
published, says nothing changed rather than pretending, and warns when a bump crosses a minor
version, because uv is pre-1.0 and minor releases may break behaviour.

To take a specific version, including one newer than the cool-down allows:

```bash
./workflow.cmd develop.bump-uv --version=0.12.1
```

**Editing any of those five by hand is the failure this command exists to avoid** — most of all
the tag, whose digest has to be re-resolved with it.

## How CI picks them up

The CI workflow installs only the group it needs for each job — `lint` job installs the `lint` group, `test` job installs `test`. This keeps job containers small and parallel-safe.

The container images built by `./workflow.cmd container.publish` cache the `dev` group's resolution so subsequent CI runs skip the install step.

## See also

- [Add a dependency](../how-to/add-a-dependency.md) — adding to any group.
- [Configuration files](configuration-files.md) — where the groups are declared.
