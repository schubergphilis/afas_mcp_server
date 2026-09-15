"""Offline checks of UpdateConnector payloads against the schema AFAS publishes for the connector."""

from collections.abc import Callable, Iterator
from typing import Any

from pydantic import BaseModel

KEY_PREFIX = '@'
FIELDS_KEY = 'Fields'
OBJECTS_KEY = 'Objects'
ELEMENT_KEY = 'Element'
ELEMENT_KEYS = (FIELDS_KEY, OBJECTS_KEY)
INSERT = 'insert'


class Issue(BaseModel):
    """One problem found in a payload."""

    path: str
    message: str


def is_integer(value: object) -> bool:
    """Return whether ``value`` is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: object) -> bool:
    """Return whether ``value`` is an int or float and not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


TYPE_CHECKS: dict[str, Callable[[object], bool]] = {
    'boolean': lambda value: isinstance(value, bool),
    'int': is_integer,
    'long': is_integer,
    'decimal': is_number,
    'string': lambda value: isinstance(value, str),
    'date': lambda value: isinstance(value, str),
    'blob': lambda value: isinstance(value, str),
}


def join_path(*parts: str) -> str:
    """Join non-empty path parts with dots."""
    return '.'.join(part for part in parts if part)


def fields_by_id(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the fields of a schema node by field id."""
    return {field['fieldId']: field for field in schema.get('fields') or [] if 'fieldId' in field}


def objects_by_name(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the nested objects of a schema node by name."""
    return {item['name']: item for item in schema.get('objects') or [] if 'name' in item}


def field_value_issues(field: dict[str, Any], value: object, path: str) -> Iterator[Issue]:
    """Yield problems with one field value: type, length and allowed values.

    Args:
        field: The field definition from the schema.
        value: The supplied value.
        path: Where the value sits in the payload.
    """
    if value is None:
        return
    data_type = str(field.get('dataType') or '')
    check = TYPE_CHECKS.get(data_type)
    if check and not check(value):
        yield Issue(path=path, message=f'expected a {data_type}, got {type(value).__name__}')
        return
    length = field.get('length') or 0
    if isinstance(value, str) and data_type == 'string' and length and len(value) > length:
        yield Issue(path=path, message=f'value is {len(value)} characters, the field allows {length}')
    allowed = [str(item['id']) for item in field.get('values') or [] if 'id' in item]
    if allowed and str(value) not in allowed:
        yield Issue(path=path, message=f'value {value!r} is not one of the allowed values {", ".join(allowed)}')


def key_issues(element: dict[str, Any], fields: dict[str, dict[str, Any]], path: str) -> Iterator[Issue]:
    """Yield problems with the ``@Key`` entries that identify a record."""
    for key, value in element.items():
        if not key.startswith(KEY_PREFIX):
            continue
        field = fields.get(key[len(KEY_PREFIX) :])
        if field is None:
            yield Issue(path=join_path(path, key), message='not a field of this connector')
        else:
            yield from field_value_issues(field, value, join_path(path, key))


def fields_issues(element: dict[str, Any], fields: dict[str, dict[str, Any]], path: str) -> Iterator[Issue]:
    """Yield problems with the ``Fields`` mapping of a record."""
    supplied = element.get(FIELDS_KEY)
    if supplied is None:
        return
    if not isinstance(supplied, dict):
        yield Issue(path=join_path(path, FIELDS_KEY), message='must be an object mapping field ids to values')
        return
    for field_id, value in supplied.items():
        field = fields.get(field_id)
        if field is None:
            yield Issue(path=join_path(path, FIELDS_KEY, field_id), message='not a field of this connector')
        else:
            yield from field_value_issues(field, value, join_path(path, FIELDS_KEY, field_id))


def mandatory_issues(element: dict[str, Any], fields: dict[str, dict[str, Any]], path: str) -> Iterator[Issue]:
    """Yield the mandatory fields an insert leaves out."""
    fields_value = element.get(FIELDS_KEY)
    supplied: dict[str, Any] = fields_value if isinstance(fields_value, dict) else {}
    keys = {key[len(KEY_PREFIX) :] for key in element if key.startswith(KEY_PREFIX)}
    for field_id, field in fields.items():
        if field.get('mandatory') and field_id not in supplied and field_id not in keys:
            yield Issue(path=join_path(path, FIELDS_KEY, field_id), message='mandatory field is missing')


def unknown_key_issues(element: dict[str, Any], path: str) -> Iterator[Issue]:
    """Yield element keys that are neither ``@Key`` entries nor ``Fields``/``Objects``."""
    for key in element:
        if not key.startswith(KEY_PREFIX) and key not in ELEMENT_KEYS:
            yield Issue(
                path=join_path(path, key), message=f'unexpected key; an Element holds {", ".join(ELEMENT_KEYS)}'
            )


def object_issues(
    name: str,
    node: object,
    objects: dict[str, dict[str, Any]],
    operation: str,
    object_path: str,
) -> Iterator[Issue]:
    """Yield problems inside one nested object: unknown name, missing ``Element``, or issues in that element."""
    schema = objects.get(name)
    if schema is None:
        yield Issue(path=object_path, message='not a nested object of this connector')
        return
    nested = node.get(ELEMENT_KEY) if isinstance(node, dict) else None
    if nested is None:
        yield Issue(path=object_path, message='must be an object with an Element')
        return
    yield from element_issues(schema, nested, operation, join_path(object_path, ELEMENT_KEY))


def objects_issues(
    element: dict[str, Any],
    objects: dict[str, dict[str, Any]],
    operation: str,
    path: str,
) -> Iterator[Issue]:
    """Yield problems inside ``Objects``, which AFAS accepts as a mapping or as a list of single-key mappings."""
    supplied = element.get(OBJECTS_KEY)
    if supplied is None:
        return
    objects_path = join_path(path, OBJECTS_KEY)
    entries = supplied if isinstance(supplied, list) else [supplied]
    for entry in entries:
        if not isinstance(entry, dict):
            yield Issue(path=objects_path, message='entries must be objects mapping an object name to its Element')
            continue
        for name, node in entry.items():
            yield from object_issues(name, node, objects, operation, join_path(objects_path, name))


def element_issues(schema: dict[str, Any], element: object, operation: str, path: str = '') -> Iterator[Issue]:
    """Yield every problem in an ``Element`` payload, recursing into nested objects.

    Args:
        schema: The connector or nested object schema from metainfo.
        element: The ``Element`` value; anything but a mapping or a list of mappings is itself reported.
        operation: ``insert`` or ``update``; only inserts must supply all mandatory fields.
        path: Where the element sits in the payload.
    """
    if isinstance(element, list):
        for index, item in enumerate(element):
            yield from element_issues(schema, item, operation, f'{path}[{index}]')
        return
    if not isinstance(element, dict):
        yield Issue(path=path or ELEMENT_KEY, message='must be an object or a list of objects')
        return
    fields = fields_by_id(schema)
    yield from unknown_key_issues(element, path)
    yield from key_issues(element, fields, path)
    yield from fields_issues(element, fields, path)
    if operation == INSERT:
        yield from mandatory_issues(element, fields, path)
    yield from objects_issues(element, objects_by_name(schema), operation, path)


def validate_element(schema: dict[str, Any], element: object, operation: str) -> list[Issue]:
    """Check an ``Element`` payload against an UpdateConnector schema without calling AFAS.

    Args:
        schema: The UpdateConnector schema as returned by ``metainfo/update/{id}``.
        element: The ``Element`` payload that would be sent; a mapping or a list of mappings.
        operation: ``insert`` or ``update``.

    Returns:
        The problems found; empty when the payload looks valid.
    """
    return list(element_issues(schema, element, operation))
