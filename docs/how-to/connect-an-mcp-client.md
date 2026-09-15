# Connect an MCP client

Register the server with the MCP client you use. All variants run the same command; they differ in where the
settings live.

## Before you start

- The connection works: `afas-mcp-server --check` prints the Profit version
  (see [Getting started](../tutorials/getting-started.md)).
- You know whether this client should be able to write. If so, read [Enable writes safely](enable-writes-safely.md)
  first.

## Claude Desktop

Add to `claude_desktop_config.json` (*Settings > Developer > Edit Config*):

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

## Claude Code

```bash
claude mcp add afas \
  -e AFAS_MEMBER_ID=12345 \
  -e AFAS_TOKEN='<token><version>1</version><data>YOUR_TOKEN_DATA</data></token>' \
  -- uvx afas-mcp-server
```

Add `--scope project` to share the entry through `.mcp.json`; keep the token out of it by referencing an
environment variable instead of a literal value.

## Cursor and other stdio clients

Any client that launches a command works with:

```json
{
  "command": "uvx",
  "args": ["afas-mcp-server"],
  "env": { "AFAS_MEMBER_ID": "12345", "AFAS_TOKEN": "..." }
}
```

## Streamable HTTP for shared deployments

Run one server for several clients:

```bash
AFAS_MEMBER_ID=12345 AFAS_TOKEN='...' afas-mcp-server --transport streamable-http --host 127.0.0.1 --port 8000
```

Clients connect to `http://127.0.0.1:8000/mcp`. The server does not authenticate HTTP clients itself, so bind it to
localhost or place it behind a reverse proxy that does, and remember that every client shares the one AFAS token.

## Use a `.env` file instead of inline variables

Create `.env` in the directory the server starts in, using [`.env.example`](https://github.com/schubergphilis/afas_mcp_server/blob/main/.env.example)
as the template. Variables set in the environment win over the file.

## Verify

Ask the assistant to run `afas_connection_info`. It returns the base URL, whether writes are enabled and the Profit
version. If the tool list is empty, check the client's log for the server's stderr output; configuration errors are
printed there with the missing variable named.
