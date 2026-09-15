# Tools

Every tool returns structured JSON. Errors from AFAS come back as tool errors carrying the AFAS `externalMessage`
and, when it adds information, the `internalMessage`.

## Read tools (always registered)

### `afas_connection_info`

No parameters. Returns `base_url`, `environment`, `member_id`, `writes_enabled`, `profit_version` (as AFAS
reports it) and `server_version`. Fails with the AFAS message when the token is rejected.

### `afas_list_connectors`

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `kind` | `all`, `get`, `update` | `all` | Which family to list. |
| `search` | string | | Keep connectors whose id or description contains this text, case-insensitively. |

Returns `get_connectors` and `update_connectors` (each a list of `{id, description}`) plus their counts.

### `afas_describe_get_connector`

| Parameter | Type | Meaning |
| --- | --- | --- |
| `connector_id` | string | GetConnector id, e.g. `Profit_Employees`. |

Returns the AFAS metainfo document unchanged: `name`, `description` and `fields`, where each field has `id`,
`fieldId`, `dataType`, `label`, `length`, `controlType` and `decimals`. Use `fieldId` values in filters and sorting.

### `afas_describe_update_connector`

| Parameter | Type | Meaning |
| --- | --- | --- |
| `connector_id` | string | UpdateConnector id, e.g. `KnSubject`. |

Returns the AFAS metainfo document unchanged: `fields` (each with `fieldId`, `primaryKey`, `dataType`, `label`,
`mandatory`, `length`, `decimals`, `notzero`, `controlType` and optional `values`) and `objects`, the nested
objects with the same structure.

### `afas_get_rows`

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `connector_id` | string | | GetConnector id. |
| `skip` | integer ≥ 0 | `0` | Rows to skip. |
| `take` | integer | `AFAS_DEFAULT_TAKE` | Rows to return, at most `AFAS_MAX_TAKE`. |
| `filters` | list of filter | | Conditions, see below. |
| `order_by` | list of string | | Field ids to sort on; prefix with `-` for descending. Always sort when paging. |

Returns `connector_id`, `skip`, `take`, `row_count`, `has_more` (true when the page was full), `next_skip` (the
`skip` for the following page, or null) and `rows`.

#### Filters

Each filter is an object:

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `field` | string | | Field id from `afas_describe_get_connector`. |
| `operator` | string | `equals` | One of the operators below. |
| `value` | string, number, boolean or null | | Value to compare with. Dates as ISO 8601. Ignored for `is_empty` and `is_not_empty`. |
| `group` | integer ≥ 0 | `0` | Filters in the same group are combined with AND; groups are combined with OR. |

| Operator | AFAS code | Notes |
| --- | --- | --- |
| `equals` | 1 | |
| `greater_or_equal` | 2 | |
| `less_or_equal` | 3 | |
| `greater_than` | 4 | |
| `less_than` | 5 | |
| `contains` | 6 | Value becomes `%value%` unless it already contains `%`. |
| `not_equals` | 7 | |
| `is_empty` | 8 | |
| `is_not_empty` | 9 | |
| `starts_with` | 10 | Value becomes `value%`. |
| `not_contains` | 11 | Value becomes `%value%`. |
| `not_starts_with` | 12 | Value becomes `value%`. |
| `ends_with` | 13 | Value becomes `%value`. |
| `not_ends_with` | 14 | Value becomes `%value`. |

Booleans are sent as `true`/`false`. When a field id or value contains `,` or `;` the server switches to the AFAS
`filterjson` syntax automatically, so such values need no escaping.

Example, "active employees in Amsterdam, or anyone named Jansen":

```json
[
  { "field": "Status", "operator": "equals", "value": "A", "group": 0 },
  { "field": "City", "operator": "equals", "value": "Amsterdam", "group": 0 },
  { "field": "LastName", "operator": "equals", "value": "Jansen", "group": 1 }
]
```

### `afas_validate_payload`

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `connector_id` | string | | UpdateConnector id. |
| `element` | object or list of objects | | The `Element` payload, see below. |
| `operation` | `insert`, `update` | `insert` | Inserts must supply every mandatory field; updates need not. |

Returns `valid`, `issues` (a list of `{path, message}`) and `body`, the exact JSON the write tools would send.

#### The `element` payload

```json
{
  "@SbId": 42,
  "Fields": { "Ds": "New description", "St": "A" },
  "Objects": {
    "KnSubjectLink": { "Element": { "Fields": { "ToPE": true } } }
  }
}
```

- `@FieldId` entries at the top level identify the record; they are required for updates.
- `Fields` maps field ids to values. `null` clears a field.
- `Objects` holds nested objects by name, each with its own `Element`; AFAS also accepts a list of such
  single-key objects.
- A list of elements sends several records in one call.

Validation reports unknown field ids and object names, missing mandatory fields on insert, values of the wrong
type, strings longer than the field allows, and values outside a field's allowed list.

## Write tools (only with `AFAS_ALLOW_WRITES=true`)

### `afas_insert`

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `connector_id` | string | | UpdateConnector id. |
| `element` | object or list | | Payload as above. |
| `validate` | boolean | `true` | Validate against the schema first; the payload is not sent when issues are found. |

HTTP POST. Returns `result`, usually the keys AFAS assigned.

### `afas_update`

Same parameters as `afas_insert`, with `@FieldId` key entries in the element. HTTP PUT. `result` is often null
because AFAS returns no body.

### `afas_delete`

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `connector_id` | string | | UpdateConnector id. |
| `key_field` | string | | Key field id, with or without the leading `@`. |
| `key_value` | string or integer | | Key of the record to delete. |
| `object_name` | string | the connector | Nested object to delete from. |

HTTP DELETE to `connectors/{connector}/{object}/@{key_field}/{key_value}`. Irreversible.

## Tool annotations

Read tools are annotated `readOnlyHint: true`. `afas_insert` is `destructiveHint: false`; `afas_update` and
`afas_delete` are `destructiveHint: true`. Clients that gate destructive tools behind a confirmation will use these.
