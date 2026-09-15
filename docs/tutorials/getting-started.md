# Getting started with AFAS MCP Server

In this tutorial you connect an AI assistant to your AFAS Profit environment and let it answer its first question
from your data. By the end you will have a running, read-only MCP server and a working Claude Desktop connection.

## You need

- An AFAS Profit environment with an app connector that has at least one GetConnector, and a token for it.
  Your AFAS administrator creates these under *Algemeen > Beheer > App connector*.
- The environment number from your AFAS Online URL: `12345` in `https://12345.afasonline.com`.
- [uv](https://docs.astral.sh/uv/) on the machine that runs the assistant.

## Step 1: Verify the connection

Put the two required settings in the environment and let the server ask AFAS for its version:

```bash
export AFAS_MEMBER_ID=12345
export AFAS_TOKEN='<token><version>1</version><data>YOUR_TOKEN_DATA</data></token>'
uvx afas-mcp-server --check
```

You should see:

```json
{
  "base_url": "https://12345.rest.afas.online/profitrestservices",
  "writes_enabled": false,
  "profit_version": { "version": "..." }
}
```

If AFAS rejects the token the server exits with code 1 and prints the AFAS message, for example `Ongeldige token`.

## Step 2: Register the server with Claude Desktop

Open Claude Desktop's settings, choose *Developer > Edit Config* and add the server:

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

Restart Claude Desktop. The hammer icon lists nine `afas_*` tools when writes are on and six when they are off,
which is the default.

## Step 3: Ask the first question

Ask: *"Which AFAS connectors can you use, and what does the employees connector contain?"*

The assistant calls `afas_list_connectors`, then `afas_describe_get_connector`, and answers with the field list.
Follow up with *"Show the first five rows sorted by name."* and it calls `afas_get_rows` with an `order_by`.

## What you just did

You gave the assistant a token-scoped window on AFAS. Everything it can see is decided by the app connector in
AFAS, and nothing it does can change data until you set `AFAS_ALLOW_WRITES=true`.

## Next steps

- [Connect an MCP client](../how-to/connect-an-mcp-client.md) for Claude Code, Cursor and HTTP deployments.
- [Enable writes safely](../how-to/enable-writes-safely.md) when the assistant should also change data.
- [Tools](../reference/tools.md) for every parameter, and [Configuration](../reference/configuration.md) for
  every setting.
