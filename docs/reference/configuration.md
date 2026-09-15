# Configuration

The server is configured through `AFAS_*` environment variables. A `.env` file in the working directory is read
too; variables set in the process environment take precedence over it. Nothing is read from command-line flags
except the transport options below.

## Environment variables

| Variable | Required | Default | Effect |
| --- | --- | --- | --- |
| `AFAS_TOKEN` | yes | | App connector token. Accepted forms: the full `<token>` XML, only the `<data>` value, or the XML already base64 encoded. |
| `AFAS_MEMBER_ID` | unless `AFAS_BASE_URL` | | AFAS Online environment number, e.g. `12345`. |
| `AFAS_ENVIRONMENT` | no | `production` | `production`, `test` or `accept`; selects the `rest`, `resttest` or `restaccept` hostname. |
| `AFAS_BASE_URL` | no | | Full REST base URL, e.g. `https://12345.rest.afas.online/profitrestservices`. Overrides `AFAS_MEMBER_ID` and `AFAS_ENVIRONMENT`. |
| `AFAS_ALLOW_WRITES` | no | `false` | Register `afas_insert`, `afas_update` and `afas_delete`. |
| `AFAS_DEFAULT_TAKE` | no | `100` | Rows per page when `afas_get_rows` is called without `take`. |
| `AFAS_MAX_TAKE` | no | `1000` | Largest `take` a call may request; larger values are refused with a tool error. |
| `AFAS_TIMEOUT_SECONDS` | no | `60` | HTTP timeout per AFAS call. |
| `AFAS_LANGUAGE` | no | `nl-nl` | `Accept-Language` sent to AFAS: `nl-nl`, `nl-be`, `fr-fr`, `de-de` or `en-us`. |
| `AFAS_LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. Logs go to stderr. |

The derived base URL is `https://{AFAS_MEMBER_ID}.{rest|resttest|restaccept}.afas.online/profitrestservices`.

## Command-line flags

| Flag | Default | Effect |
| --- | --- | --- |
| `--transport {stdio,streamable-http}` | `stdio` | How MCP clients connect. |
| `--host` | `127.0.0.1` | Bind address for streamable HTTP. |
| `--port` | `8000` | Port for streamable HTTP. |
| `--path` | `/mcp` | URL path for streamable HTTP. |
| `--check` | off | Ask AFAS for its version, print a JSON report and exit; 0 on success, 1 when AFAS or the network refuses. |
| `--version` | | Print the version and exit. |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Normal exit. |
| `1` | `--check` could not reach AFAS or AFAS rejected the token. |
| `2` | Configuration invalid; the missing or malformed variables are named on stderr. |

## See also

- [Tools](tools.md): every tool and its parameters.
- [API](api.md): the Python API, generated from docstrings.
