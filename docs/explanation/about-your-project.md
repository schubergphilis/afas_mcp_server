# About AFAS MCP Server

AFAS Profit holds the HR, payroll, finance and CRM data of tens of thousands of organisations, and its REST
connectors are how that data leaves the system. The Model Context Protocol is how AI assistants call tools.
This project is the small, honest piece between the two.

## What problem does it solve?

People who work with AFAS data spend their days answering questions such as "which employees changed cost centre
last month" or "which debtors have overdue invoices in Utrecht". Each answer means finding the right GetConnector,
knowing its field ids, writing a filter in AFAS's numeric operator syntax and paging through the result. An
assistant can do that work if it can see the connectors. Existing options were hosted proxies that put a third
party between you and your ERP, or building a one-off integration. This server runs where you run it, uses your
token and nothing else, and is small enough to audit in an afternoon.

## How it works, at a glance

- `configuration.py` reads `AFAS_*` settings and encodes the token the way AFAS wants it.
- `client.py` is a thin asynchronous client for the REST services: metainfo, GetConnectors, UpdateConnectors, and
  error decoding including the base64 `X-PROFIT-ERROR` header.
- `filters.py` turns readable filter objects into the `filterfieldids`/`filtervalues`/`operatortypes` query
  string, or into `filterjson` when a value contains a separator.
- `validation.py` checks an UpdateConnector payload against the schema AFAS publishes for it, offline.
- `server.py` registers the tools with the MCP SDK and translates AFAS errors into tool errors the model can read.
- `__main__.py` is the command line: stdio or streamable HTTP, plus `--check`.

One AFAS client lives for the lifetime of the server and is shared by all tool calls.

## Key design decisions

- **Read-only unless asked.** The write tools are not merely refused, they are not registered without
  `AFAS_ALLOW_WRITES=true`. A model cannot be talked into calling a tool it cannot see, and an operator can tell
  from the tool list alone what a server can do. The alternative, a permission flag checked inside each tool, would
  leave the tools visible and the decision to a prompt.
- **No bundled connector knowledge.** The server discovers connectors and fields through metainfo at call time
  rather than shipping a catalogue. AFAS environments differ in which connectors exist and what they contain; a
  catalogue would be wrong somewhere on day one. The price is one extra call per describe, which AFAS answers fast.
- **Validate before writing, on the client side.** AFAS validates too, but its error messages come after the
  request and one at a time. Checking the payload against the schema first lets the model fix every problem at
  once and, in `afas_validate_payload`, lets a user see the exact body before anything is sent. It is a safety net,
  not a guarantee: business rules only AFAS knows still apply, so `validate: false` exists for schemas that are
  incomplete.
- **Filters by name, grouped by number.** Operators are words (`contains`) rather than AFAS codes (6), and the
  AND/OR structure is expressed with a `group` number per filter. That is a flat list a model produces reliably,
  and it maps one-to-one onto AFAS's comma-and-semicolon syntax. Nested boolean trees were considered and
  rejected as harder for models to emit correctly and no more expressive than what AFAS supports.
- **Pass AFAS metainfo through unchanged.** Describe tools return AFAS's own JSON rather than a normalised shape,
  so documentation AFAS publishes about a field applies verbatim and nothing is lost in translation.
- **One token per server.** The server authenticates to AFAS with the token it was started with, for every client.
  Per-user AFAS identity would need OAuth-style delegation AFAS does not offer for app connectors; the honest
  alternative is to run one server per token, which the configuration makes cheap.

## How it is maintained

The repository is maintained by an AI agent under human supervision, following the rules in
[`AGENTS.md`](https://github.com/schubergphilis/afas_mcp_server/blob/main/AGENTS.md). The reasoning:

- **The work is mostly churn, not design.** The MCP SDK moves quickly, the Python tooling moves
  weekly, AFAS itself moves slowly. Keeping up is a steady stream of small, well-tested changes,
  which is what an agent with a strong test suite does well and what volunteers do badly.
- **Humans keep the judgement calls.** Releases, publishing, anything verified against a real
  AFAS environment, license decisions and security disclosures stay with people. The agent
  prepares; a human decides.
- **Dependabot rather than Renovate.** Both would do. Dependabot is built into GitHub, needs
  no app installed on the organisation, its `cooldown` gives the seven-day release quarantine
  this project's conventions ask for, and its alerts already feed the Security tab.
- **The template's fixed `exclude-newer` date is gone.** It made uv refuse any newer package,
  which would have turned every Dependabot lock update into a failure. The quarantine moved to
  Dependabot, where it gates what gets proposed; reproducibility comes from exact pins and
  `uv.lock`. See [Dependency groups](../developer/reference/dependency-groups.md).

## License

Apache-2.0. Every runtime dependency in the lockfile is MIT, BSD-3-Clause, Apache-2.0, PSF-2.0
or MIT-0, so nothing forces a copyleft license and any permissive one would have been possible.
Apache-2.0 was chosen over MIT because it adds an explicit patent grant, it is the license of
every other Schuberg Philis open-source repository, and it is what the project template emits.
AFAS and AFAS Profit are trademarks of AFAS Software B.V.; this project is not affiliated with
AFAS.

## Scope and non-goals

- Not a general AFAS SDK. The client covers what the tools need; use it if it fits, but completeness is not a goal.
- No SOAP, no Insite or Outsite, no file, image or report connectors in this version. They are candidates once
  someone needs them.
- No caching of rows or schemas. AFAS is the source of truth, and staleness in an assistant's answer is worse than
  an extra call.
- No authentication for the HTTP transport. Deployments that need it already have a reverse proxy that does it
  better.

## See also

- [Tools](../reference/tools.md) and [Configuration](../reference/configuration.md).
- [The scaffold](../developer/index.md): the tooling this project inherited from its template.
