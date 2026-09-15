"""Tests for rendering GetConnector filters and sort order."""

import json

import pytest

from afas_mcp_server.filters import (
    OPERATOR_CODES,
    Filter,
    FilterValue,
    Operator,
    filter_params,
    order_by_param,
    query_params,
)


def test_every_operator_has_a_unique_afas_code() -> None:
    """AFAS defines operator types 1 through 14; each name maps onto exactly one."""
    assert sorted(OPERATOR_CODES.values()) == list(range(1, 15))
    assert {operator.code for operator in Operator} == set(range(1, 15))


@pytest.mark.parametrize(
    ('operator', 'value', 'expected'),
    [
        (Operator.EQUALS, 'Amsterdam', 'Amsterdam'),
        (Operator.CONTAINS, 'dam', '%dam%'),
        (Operator.NOT_CONTAINS, 'dam', '%dam%'),
        (Operator.STARTS_WITH, 'Ams', 'Ams%'),
        (Operator.NOT_STARTS_WITH, 'Ams', 'Ams%'),
        (Operator.ENDS_WITH, 'dam', '%dam'),
        (Operator.NOT_ENDS_WITH, 'dam', '%dam'),
        (Operator.CONTAINS, 'A%m', 'A%m'),
        (Operator.EQUALS, 42, '42'),
        (Operator.EQUALS, 12.5, '12.5'),
        (Operator.EQUALS, True, 'true'),
        (Operator.EQUALS, False, 'false'),
        (Operator.IS_EMPTY, 'ignored', ''),
        (Operator.IS_NOT_EMPTY, None, ''),
        (Operator.EQUALS, None, ''),
    ],
)
def test_rendered_value(operator: Operator, value: FilterValue, expected: str) -> None:
    """Values are rendered as text, with wildcards for the text operators."""
    assert Filter(field='City', operator=operator, value=value).rendered_value == expected


def test_and_filters_use_commas() -> None:
    """Filters in the same group are joined with commas in all three parameters."""
    params = filter_params(
        [
            Filter(field='City', value='Amsterdam'),
            Filter(field='Name', operator=Operator.CONTAINS, value='Jan'),
        ]
    )
    assert params == {'filterfieldids': 'City,Name', 'filtervalues': 'Amsterdam,%Jan%', 'operatortypes': '1,6'}


def test_or_groups_use_semicolons() -> None:
    """Different group numbers become alternatives separated by semicolons."""
    params = filter_params(
        [
            Filter(field='Status', value='A', group=0),
            Filter(field='City', value='Utrecht', group=0),
            Filter(field='Status', value='B', group=1),
        ]
    )
    assert params == {
        'filterfieldids': 'Status,City;Status',
        'filtervalues': 'A,Utrecht;B',
        'operatortypes': '1,1;1',
    }


def test_groups_are_ordered_by_number_not_by_appearance() -> None:
    """Group order follows the group number so the rendering is deterministic."""
    params = filter_params([Filter(field='A', value='1', group=2), Filter(field='B', value='2', group=1)])
    assert params['filterfieldids'] == 'B;A'


def test_empty_check_keeps_its_slot_in_the_value_list() -> None:
    """AFAS requires a (possibly empty) value for is_empty, so the slot must stay."""
    params = filter_params([Filter(field='A', value='x'), Filter(field='B', operator=Operator.IS_EMPTY)])
    assert params['filtervalues'] == 'x,'
    assert params['operatortypes'] == '1,8'


def test_separator_in_value_switches_to_json_filter() -> None:
    """Commas and semicolons cannot be escaped in the compact syntax, so filterjson is used instead."""
    params = filter_params(
        [
            Filter(field='Name', value='Jansen, Jan', group=0),
            Filter(field='City', operator=Operator.STARTS_WITH, value='Ams', group=1),
        ]
    )
    assert set(params) == {'filterjson'}
    payload = json.loads(params['filterjson'])
    assert payload == {
        'Filters': {
            'Filter': [
                {
                    '@FilterId': 'Filter 1',
                    'Field': [{'@FieldId': 'Name', '@OperatorType': '1', '#text': 'Jansen, Jan'}],
                },
                {'@FilterId': 'Filter 2', 'Field': [{'@FieldId': 'City', '@OperatorType': '10', '#text': 'Ams%'}]},
            ]
        }
    }


def test_no_filters_means_no_parameters() -> None:
    """None and an empty list both render to nothing."""
    assert not filter_params(None)
    assert not filter_params([])


def test_order_by_joins_fields_and_keeps_descending_prefix() -> None:
    """A leading minus marks descending order, exactly as AFAS expects."""
    assert order_by_param(['Name', ' -Date ']) == {'orderbyfieldids': 'Name,-Date'}


def test_order_by_without_fields_renders_nothing() -> None:
    """Blank entries are dropped and an empty result adds no parameter."""
    assert not order_by_param(None)
    assert not order_by_param(['', '  '])


def test_query_params_combine_paging_filters_and_order() -> None:
    """The full query string is paging first, then filters, then sorting."""
    params = query_params(skip=20, take=10, filters=[Filter(field='A', value=1)], order_by=['A'])
    assert params == {
        'skip': '20',
        'take': '10',
        'filterfieldids': 'A',
        'filtervalues': '1',
        'operatortypes': '1',
        'orderbyfieldids': 'A',
    }


def test_filter_rejects_negative_group() -> None:
    """Group numbers are non-negative so the rendering order stays obvious."""
    with pytest.raises(ValueError, match='group'):
        Filter(field='A', group=-1)
