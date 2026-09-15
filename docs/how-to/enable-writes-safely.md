# Enable writes safely

Let the assistant create, change or delete records in AFAS without giving it more power than the task needs.

## Before you start

- A read-only setup works (see [Connect an MCP client](connect-an-mcp-client.md)).
- You have, or can get, an AFAS **test** environment and a separate app connector for writing.

## Steps

1. Create a dedicated app connector in AFAS with only the UpdateConnectors the assistant needs, and a token for a
   user whose AFAS permissions match. Do not reuse the read-only token.

2. Point a separate server instance at the test environment with writes enabled:

   ```bash
   export AFAS_ENVIRONMENT=test
   export AFAS_ALLOW_WRITES=true
   afas-mcp-server --check
   ```

   The report shows `"writes_enabled": true`.

3. Register this instance under a distinct name in your client, for example `afas-write`, so the assistant and you
   can tell the two apart.

4. Let the assistant rehearse without sending: ask it to call `afas_describe_update_connector` and then
   `afas_validate_payload` for the change. The result lists every schema problem and the exact JSON body that would
   go to AFAS.

5. Only then ask for the change. `afas_insert` and `afas_update` validate again before sending unless the call sets
   `validate: false`; `afas_delete` needs the key field and value and is irreversible.

6. Verify in AFAS, then repeat against production by switching `AFAS_ENVIRONMENT` back to `production`.

## What the assistant is told

With writes enabled the server's instructions ask the model to describe the connector, validate the payload, show
the user what will change, and confirm deletions before acting. The write tools are also annotated as not read-only
and, for update and delete, as destructive, so clients that ask for confirmation on such tools will do so.

## See also

- [Tools](../reference/tools.md) for the exact payload shape of `element`.
- [Configuration](../reference/configuration.md) for every variable used above.
