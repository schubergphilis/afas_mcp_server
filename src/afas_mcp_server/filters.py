"""Filter, sort and paging expressions for GetConnector calls, rendered the way the AFAS REST API expects them."""

import json
from enum import Enum

from pydantic import BaseModel, Field

AND_SEPARATOR = ','
OR_SEPARATOR = ';'
WILDCARD = '%'
SEPARATORS = (AND_SEPARATOR, OR_SEPARATOR)

# int is listed before float on purpose: pydantic keeps 42 an int, so it renders as "42" rather than "42.0".
FilterValue = str | int | float | bool | None


class Operator(str, Enum):
    """Comparison operators AFAS supports in GetConnector filters, by readable name."""

    EQUALS = 'equals'
    GREATER_OR_EQUAL = 'greater_or_equal'
    LESS_OR_EQUAL = 'less_or_equal'
    GREATER_THAN = 'greater_than'
    LESS_THAN = 'less_than'
    CONTAINS = 'contains'
    NOT_EQUALS = 'not_equals'
    IS_EMPTY = 'is_empty'
    IS_NOT_EMPTY = 'is_not_empty'
    STARTS_WITH = 'starts_with'
    NOT_CONTAINS = 'not_contains'
    NOT_STARTS_WITH = 'not_starts_with'
    ENDS_WITH = 'ends_with'
    NOT_ENDS_WITH = 'not_ends_with'

    @property
    def code(self) -> int:
        """The numeric ``operatortypes`` value AFAS uses for this operator."""
        return OPERATOR_CODES[self]


OPERATOR_CODES = {
    Operator.EQUALS: 1,
    Operator.GREATER_OR_EQUAL: 2,
    Operator.LESS_OR_EQUAL: 3,
    Operator.GREATER_THAN: 4,
    Operator.LESS_THAN: 5,
    Operator.CONTAINS: 6,
    Operator.NOT_EQUALS: 7,
    Operator.IS_EMPTY: 8,
    Operator.IS_NOT_EMPTY: 9,
    Operator.STARTS_WITH: 10,
    Operator.NOT_CONTAINS: 11,
    Operator.NOT_STARTS_WITH: 12,
    Operator.ENDS_WITH: 13,
    Operator.NOT_ENDS_WITH: 14,
}

# AFAS documents these text operators with explicit wildcards around the value.
WILDCARD_TEMPLATES = {
    Operator.CONTAINS: '%{value}%',
    Operator.NOT_CONTAINS: '%{value}%',
    Operator.STARTS_WITH: '{value}%',
    Operator.NOT_STARTS_WITH: '{value}%',
    Operator.ENDS_WITH: '%{value}',
    Operator.NOT_ENDS_WITH: '%{value}',
}

VALUELESS_OPERATORS = (Operator.IS_EMPTY, Operator.IS_NOT_EMPTY)


class Filter(BaseModel):
    """One condition on a GetConnector column."""

    field: str = Field(description='Technical field id of the column, as listed by afas_describe_get_connector.')
    operator: Operator = Field(
        default=Operator.EQUALS,
        description='Comparison to apply. Text operators add % wildcards automatically unless the value has them.',
    )
    value: FilterValue = Field(
        default=None,
        description='Value to compare with. Dates as ISO 8601 (2024-01-31). Ignored for is_empty and is_not_empty.',
    )
    group: int = Field(
        default=0,
        ge=0,
        description='Conditions sharing a group number are combined with AND; different groups are combined with OR.',
    )

    @property
    def rendered_value(self) -> str:
        """The value as text, with the wildcards AFAS expects for the text operators."""
        if self.operator in VALUELESS_OPERATORS or self.value is None:
            return ''
        if isinstance(self.value, bool):
            return 'true' if self.value else 'false'
        text = str(self.value)
        template = WILDCARD_TEMPLATES.get(self.operator)
        if template and WILDCARD not in text:
            return template.format(value=text)
        return text


def filter_groups(filters: list[Filter]) -> list[list[Filter]]:
    """Bucket filters by group number, in ascending group order.

    Args:
        filters: The conditions to bucket.

    Returns:
        One list per group; filters within a list are ANDed, lists are ORed.
    """
    groups: dict[int, list[Filter]] = {}
    for item in filters:
        groups.setdefault(item.group, []).append(item)
    return [groups[key] for key in sorted(groups)]


def needs_json_filter(filters: list[Filter]) -> bool:
    """Return whether any field or value contains a separator, which the compact syntax cannot escape.

    Args:
        filters: The conditions to inspect.

    Returns:
        True when the JSON filter syntax must be used.
    """
    return any(
        separator in item.field or separator in item.rendered_value for item in filters for separator in SEPARATORS
    )


def compact_filter_params(groups: list[list[Filter]]) -> dict[str, str]:
    """Render filters as the ``filterfieldids``/``filtervalues``/``operatortypes`` query parameters.

    Args:
        groups: Filters bucketed by ``filter_groups``.

    Returns:
        The three query parameters, with ``,`` between AND conditions and ``;`` between OR groups.
    """
    return {
        'filterfieldids': OR_SEPARATOR.join(AND_SEPARATOR.join(item.field for item in group) for group in groups),
        'filtervalues': OR_SEPARATOR.join(
            AND_SEPARATOR.join(item.rendered_value for item in group) for group in groups
        ),
        'operatortypes': OR_SEPARATOR.join(
            AND_SEPARATOR.join(str(item.operator.code) for item in group) for group in groups
        ),
    }


def json_filter_params(groups: list[list[Filter]]) -> dict[str, str]:
    """Render filters as the ``filterjson`` query parameter.

    Args:
        groups: Filters bucketed by ``filter_groups``.

    Returns:
        A single ``filterjson`` parameter with one ``Filter`` entry per OR group.
    """
    payload = {
        'Filters': {
            'Filter': [
                {
                    '@FilterId': f'Filter {index}',
                    'Field': [
                        {'@FieldId': item.field, '@OperatorType': str(item.operator.code), '#text': item.rendered_value}
                        for item in group
                    ],
                }
                for index, group in enumerate(groups, start=1)
            ]
        }
    }
    return {'filterjson': json.dumps(payload, separators=(',', ':'), ensure_ascii=False)}


def filter_params(filters: list[Filter] | None) -> dict[str, str]:
    """Render filters as query parameters, picking the compact syntax unless a separator forces JSON.

    Args:
        filters: The conditions to render, or None for no filtering.

    Returns:
        Query parameters to add to the GetConnector request.
    """
    if not filters:
        return {}
    groups = filter_groups(filters)
    if needs_json_filter(filters):
        return json_filter_params(groups)
    return compact_filter_params(groups)


def order_by_param(order_by: list[str] | None) -> dict[str, str]:
    """Render the sort order as the ``orderbyfieldids`` query parameter.

    Args:
        order_by: Field ids to sort on; prefix with ``-`` for descending.

    Returns:
        The query parameter, or nothing when no sort order was given.
    """
    fields = [item.strip() for item in order_by or [] if item.strip()]
    if not fields:
        return {}
    return {'orderbyfieldids': AND_SEPARATOR.join(fields)}


def query_params(
    *,
    skip: int,
    take: int,
    filters: list[Filter] | None = None,
    order_by: list[str] | None = None,
) -> dict[str, str]:
    """Build the complete query string for a GetConnector call.

    Args:
        skip: Number of rows to skip.
        take: Number of rows to return.
        filters: Conditions to apply, if any.
        order_by: Sort order, if any.

    Returns:
        All query parameters for the request.
    """
    params = {'skip': str(skip), 'take': str(take)}
    params.update(filter_params(filters))
    params.update(order_by_param(order_by))
    return params
