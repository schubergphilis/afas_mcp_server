# Contributing

Thank you for helping make AFAS data usable by AI assistants. This project is maintained by an AI
agent under human supervision, so the rules below are written to be checkable, not because we
distrust you: the same rules bind the agent.

## Before you start

- Read [AGENTS.md](AGENTS.md). It is the maintainer manual and lists the non-negotiables
  (read-only by default, no credentials anywhere, Apache-2.0 dependencies only).
- Search the [issues](https://github.com/schubergphilis/afas_mcp_server/issues) first. For
  anything larger than a bug fix, open an issue describing the problem before writing code, so
  the design can be discussed.
- Security problems go to [SECURITY.md](SECURITY.md), never to a public issue.

## Development setup

You need [uv](https://docs.astral.sh/uv/). Everything else is installed on first use.

```bash
git clone https://github.com/schubergphilis/afas_mcp_server
cd afas_mcp_server
./workflow.cmd --list          # bootstraps the environment and shows every task
./workflow.cmd lint
./workflow.cmd test
```

`./workflow.cmd` wraps uv and the pinned tools; on Windows the same file works from PowerShell
or cmd. If your uv version differs from `[tool.uv] required-version` in `pyproject.toml`, run
the pinned one with `uvx uv@<version> run ...` instead of upgrading or downgrading globally.

To try the server against a real AFAS environment, copy `.env.example` to `.env`, fill in a
token for a **test** environment, and run `uv run afas-mcp-server --check`.

## Making a change

1. Branch from `main`.
2. Write the test first when you can; the suite drives the server through an in-process MCP
   client against a fake AFAS, so most behaviour is testable without credentials
   (see `tests/test_server.py`).
3. Keep `./workflow.cmd format`, `lint`, `test` and `quality` green. Coverage is at 100% and the
   ratchet does not let it drop.
4. Update the docs in the same change: `docs/reference/tools.md` for tool behaviour,
   `docs/reference/configuration.md` for settings, and the how-to or explanation pages when the
   change affects how people use or understand the server.
5. Commit with a [Conventional Commits](https://www.conventionalcommits.org/) message
   (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`, `ci:`, `chore:`). The changelog is
   generated from these.
6. Open a pull request. Fill in the template; CI runs lint, tests across Python 3.10 to 3.14, a
   dependency audit and a build.

The maintainer agent may review your PR, ask questions, or push a follow-up commit to fix lint
findings; a human still merges anything that changes behaviour. If something the agent says is
wrong, say so in the PR: it is instructed to defer to humans.

## What we are unlikely to accept

- Anything that makes writing to AFAS possible without `AFAS_ALLOW_WRITES=true`.
- Bundled connector catalogues or field lists; the server discovers those from AFAS metainfo.
- Dependencies with copyleft or unclear licenses.
- Features that need per-user AFAS identity; the server deliberately uses one token per process.

See [About AFAS MCP Server](docs/explanation/about-your-project.md) for the reasoning behind
these boundaries.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind; assume good faith.
