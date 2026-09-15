# AFAS MCP Server

[![Version](https://img.shields.io/badge/version-0.0.0-blue)](https://pypi.org/project/afas_mcp_server/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue?logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](https://opensource.org/license/apache-2.0)
[![Documentation: Diátaxis](https://img.shields.io/badge/docs-Di%C3%A1taxis-009485?logo=readthedocs&logoColor=white)](https://diataxis.fr/)
[![Build](https://img.shields.io/badge/build-unknown-lightgrey)](https://github.com/features/actions)
[![Coverage](https://img.shields.io/badge/coverage-unknown-lightgrey)](https://coverage.readthedocs.io/)
[![pyscn quality](https://img.shields.io/badge/pyscn-not%20rated-lightgrey)](https://pyscn.ludo-tech.org)

An open-source [Model Context Protocol](https://modelcontextprotocol.io) server for [AFAS Profit](https://www.afas.nl).
It lets AI assistants such as Claude Desktop, Claude Code, Cursor or any other MCP client read data through your
GetConnectors, inspect connector schemas, and, only when you switch it on, write through UpdateConnectors.

- **Read-only by default.** Insert, update and delete tools exist only when `AFAS_ALLOW_WRITES=true`.
- **Your connectors, your rules.** The server sees exactly the GetConnectors and UpdateConnectors that the AFAS app
  connector behind the token allows. Nothing is bundled or hard-coded.
- **Schema-aware.** Field definitions come from AFAS metainfo, and write payloads are validated against the
  UpdateConnector schema before anything is sent.
- **Readable filters.** Filters are expressed by field id and operator name (`contains`, `greater_than`, ...) and
  rendered into the AFAS query syntax, including OR groups and the JSON filter fallback.
- **Runs anywhere an MCP client does.** stdio for desktop clients, streamable HTTP for shared deployments.

## Quick start

1. In AFAS Profit, create an app connector (*Algemeen > Beheer > App connector*), add the GetConnectors and
   UpdateConnectors the assistant may use, and create a token for a user. Note the environment number from your
   AFAS Online URL, e.g. `12345` in `https://12345.afasonline.com`.

2. Install [uv](https://docs.astral.sh/uv/) and verify the connection:

   ```bash
   export AFAS_MEMBER_ID=12345
   export AFAS_TOKEN='<token><version>1</version><data>YOUR_TOKEN_DATA</data></token>'
   uvx afas-mcp-server --check
   ```

   You should see the base URL the server will talk to and the Profit version AFAS reports.

3. Register the server with your MCP client. For Claude Desktop, add this to `claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "afas": {
         "command": "uvx",
         "args": ["afas-mcp-server"],
         "env": {
           "AFAS_MEMBER_ID": "12345",
           "AFAS_TOKEN": "<token><version>1</version><data>YOUR_TOKEN_DATA</data></token>"
         }
       }
     }
   }
   ```

   For Claude Code:

   ```bash
   claude mcp add afas -e AFAS_MEMBER_ID=12345 -e AFAS_TOKEN='<token>...</token>' -- uvx afas-mcp-server
   ```

4. Ask your assistant something like *"Which AFAS connectors can you use?"* or *"Show the ten most recently
   changed employees."* It will discover connectors, read their field definitions and page through rows.

Until the package is published on PyPI, run it from a checkout instead: `uv run afas-mcp-server`, or from git with
`uvx --from git+https://github.com/schubergphilis/afas_mcp_server afas-mcp-server`.

## Tools

| Tool | Changes data | Purpose |
| --- | --- | --- |
| `afas_connection_info` | no | Which environment the server talks to; proves the token works. |
| `afas_list_connectors` | no | GetConnectors and UpdateConnectors available to the token, with keyword search. |
| `afas_describe_get_connector` | no | Field ids, labels, types and lengths of a GetConnector. |
| `afas_describe_update_connector` | no | Fields, mandatory flags, allowed values and nested objects of an UpdateConnector. |
| `afas_get_rows` | no | One page of rows with filters, sort order and paging metadata. |
| `afas_validate_payload` | no | Check an UpdateConnector payload against its schema and show the body that would be sent. |
| `afas_insert` | **yes** | Create records (HTTP POST). Only with `AFAS_ALLOW_WRITES=true`. |
| `afas_update` | **yes** | Change records (HTTP PUT). Only with `AFAS_ALLOW_WRITES=true`. |
| `afas_delete` | **yes** | Delete one record (HTTP DELETE). Only with `AFAS_ALLOW_WRITES=true`. |

The full parameter reference is in [docs/reference/tools.md](docs/reference/tools.md).

## Configuration

Settings come from `AFAS_*` environment variables or a `.env` file in the working directory
(see [`.env.example`](https://github.com/schubergphilis/afas_mcp_server/blob/main/.env.example)).

| Variable | Default | Effect |
| --- | --- | --- |
| `AFAS_TOKEN` | required | App connector token: the `<token>` XML, only its `<data>` value, or the base64 form. |
| `AFAS_MEMBER_ID` | | AFAS Online environment number. Required unless `AFAS_BASE_URL` is set. |
| `AFAS_ENVIRONMENT` | `production` | `production`, `test` or `accept`; selects `rest`, `resttest` or `restaccept`. |
| `AFAS_BASE_URL` | | Full REST base URL; overrides member id and environment. |
| `AFAS_ALLOW_WRITES` | `false` | Register the insert, update and delete tools. |
| `AFAS_DEFAULT_TAKE` | `100` | Rows per page when a call gives no `take`. |
| `AFAS_MAX_TAKE` | `1000` | Largest `take` a call may request. |
| `AFAS_TIMEOUT_SECONDS` | `60` | HTTP timeout per AFAS call. |
| `AFAS_LANGUAGE` | `nl-nl` | Language of AFAS messages: `nl-nl`, `nl-be`, `fr-fr`, `de-de` or `en-us`. |
| `AFAS_LOG_LEVEL` | `INFO` | Log level; logs go to stderr so stdio stays clean. |

Command line: `afas-mcp-server [--transport stdio|streamable-http] [--host H] [--port P] [--path /mcp] [--check]`.

## Writing to AFAS

Writes are off until you set `AFAS_ALLOW_WRITES=true`. With writes on, the assistant is instructed to describe the
UpdateConnector, validate the payload and show the change before sending it, and every write tool validates the
payload against the schema first (switch off per call with `validate: false`). Recommended practice:

- Start against your AFAS **test** environment (`AFAS_ENVIRONMENT=test`).
- Give the token an app connector with only the connectors the assistant needs.
- Keep separate tokens, and separate server instances, for read-only and writing use.

## Security notes

- The token is a credential for your ERP and HR data. Keep it in environment variables or a `.env` file that is not
  committed; never paste it into a prompt.
- The server forwards calls to AFAS and nothing else. It stores no data and calls no other service.
- The streamable HTTP transport has no authentication of its own. Bind it to localhost or put it behind a reverse
  proxy that authenticates clients.

## How this repository is maintained

An AI agent, running as the [Claude Code GitHub Action](https://code.claude.com/docs/en/github-actions), maintains
this repository under human supervision. Its standing instructions are in [AGENTS.md](https://github.com/schubergphilis/afas_mcp_server/blob/main/AGENTS.md): what it must never
do (make writing possible by default, touch credentials, add a non-permissive dependency, push to `main`, publish),
how it runs the checks, and the weekly checklist it works through.

- **Dependencies.** Dependabot proposes updates every Monday after a seven-day release cooldown. A workflow merges
  GitHub Actions and non-major tooling updates once CI is green; the agent reviews runtime dependencies and major
  bumps, fixes the code when an update breaks it, and approves or asks a human.
- **Health.** Every week the agent checks failing builds, security audit findings, expiring audit overrides,
  untriaged issues and a stale lockfile, opens pull requests for what it can fix, and posts a summary on the
  *Maintenance log* issue.
- **Requests.** Maintainers ask for changes with `@claude` in any issue or pull request. Text from people without
  write access is treated as data, never as instructions.
- **Humans decide** releases, publishing, anything verified against a real AFAS environment, license questions and
  security disclosures.

Contributors follow the same rules; see [CONTRIBUTING.md](https://github.com/schubergphilis/afas_mcp_server/blob/main/CONTRIBUTING.md). The wiring and the repository settings
it relies on are described in [Maintain the repository with an agent](docs/developer/how-to/maintain-with-an-agent.md).

## Documentation

Full documentation lives in [`docs/`](docs/index.md): build and open it with `./workflow.cmd document`, or read it
online at <https://schubergphilis.github.io/afas_mcp_server/> once GitHub Pages is enabled for the repository.

## Developing

> Development flow as [Paleofuturistic Python](https://github.com/schubergphilis/paleofuturistic_python)

Prerequisite: [uv](https://docs.astral.sh/uv/). Every development action runs through `./workflow.cmd <task>`: the
first run bootstraps the environment automatically. `./workflow.cmd lint` and `./workflow.cmd test` are the two you
will use most.

The scaffold manual lives in the docs' **Developer** section: start with
[First-run setup](docs/developer/tutorials/first-run-setup.md); the full command list is in the
[Invoke task catalog](docs/developer/reference/invoke-tasks.md).

## License

Apache-2.0. AFAS and AFAS Profit are trademarks of AFAS Software B.V.; this project is not affiliated with AFAS.
