"""Tests for offline validation of UpdateConnector payloads."""

from typing import Any

from afas_mcp_server.validation import Issue, validate_element


def paths(issues: list[Issue]) -> list[str]:
    """The paths of the issues, for compact assertions."""
    return [issue.path for issue in issues]


def test_valid_insert_has_no_issues(update_schema: dict[str, Any]) -> None:
    """A payload with all mandatory fields and valid values passes."""
    element = {'Fields': {'StId': 1, 'Ds': 'Hello', 'Bl': True, 'Am': 12.5, 'St': 'A'}}
    assert not validate_element(update_schema, element, 'insert')


def test_insert_reports_missing_mandatory_fields(update_schema: dict[str, Any]) -> None:
    """Inserts must supply every mandatory field."""
    issues = validate_element(update_schema, {'Fields': {'Ds': 'x'}}, 'insert')
    assert paths(issues) == ['Fields.StId']
    assert 'mandatory' in issues[0].message


def test_update_does_not_require_mandatory_fields(update_schema: dict[str, Any]) -> None:
    """Updates send only the key and the changed fields."""
    assert not validate_element(update_schema, {'@SbId': 5, 'Fields': {'Ds': 'x'}}, 'update')


def test_key_counts_as_supplied_mandatory_field(update_schema: dict[str, Any]) -> None:
    """A mandatory field given as @Key at element level is not reported missing."""
    assert not validate_element(update_schema, {'@StId': 1, 'Fields': {'Ds': 'x'}}, 'insert')


def test_unknown_field_and_key_are_reported(update_schema: dict[str, Any]) -> None:
    """Typos in field ids are the most common mistake, so they are named."""
    issues = validate_element(update_schema, {'@Nope': 1, 'Fields': {'Bogus': 1}}, 'update')
    assert paths(issues) == ['@Nope', 'Fields.Bogus']


def test_type_length_and_enumeration_checks(update_schema: dict[str, Any]) -> None:
    """Wrong types, over-long strings and values outside the allowed list are reported."""
    element = {'Fields': {'StId': 'one', 'Ds': 'far too long text', 'Bl': 'yes', 'Am': True, 'St': 'Z'}}
    issues = validate_element(update_schema, element, 'update')
    by_path = {issue.path: issue.message for issue in issues}
    assert by_path['Fields.StId'] == 'expected a int, got str'
    assert by_path['Fields.Ds'] == 'value is 17 characters, the field allows 10'
    assert by_path['Fields.Bl'] == 'expected a boolean, got str'
    assert by_path['Fields.Am'] == 'expected a decimal, got bool'
    assert 'allowed values A, I' in by_path['Fields.St']


def test_null_values_are_accepted(update_schema: dict[str, Any]) -> None:
    """Null clears a field in AFAS, so it is valid for any type."""
    assert not validate_element(update_schema, {'Fields': {'Ds': None, 'Bl': None}}, 'update')


def test_fields_must_be_a_mapping(update_schema: dict[str, Any]) -> None:
    """A list where a mapping is expected is reported once, not per item."""
    issues = validate_element(update_schema, {'Fields': ['Ds']}, 'update')
    assert paths(issues) == ['Fields']


def test_unexpected_element_keys_are_reported(update_schema: dict[str, Any]) -> None:
    """Fields placed directly on the Element instead of under Fields are a classic mistake."""
    issues = validate_element(update_schema, {'Ds': 'x', 'Fields': {'Ds': 'x'}}, 'update')
    assert paths(issues) == ['Ds']


def test_nested_objects_are_validated_recursively(update_schema: dict[str, Any]) -> None:
    """Nested Objects follow the sub-schema, including their mandatory fields on insert."""
    element = {
        'Fields': {'StId': 1, 'Ds': 'x'},
        'Objects': {'KnSubjectLink': {'Element': {'Fields': {'DoCRM': True}}}},
    }
    issues = validate_element(update_schema, element, 'insert')
    assert paths(issues) == ['Objects.KnSubjectLink.Element.Fields.ToPE']


def test_objects_may_be_a_list_of_single_key_mappings(update_schema: dict[str, Any]) -> None:
    """AFAS accepts Objects as a list as well as a mapping."""
    element = {
        'Fields': {'StId': 1, 'Ds': 'x'},
        'Objects': [{'KnSubjectLink': {'Element': [{'Fields': {'ToPE': True}}, {'Fields': {'ToPE': 'no'}}]}}],
    }
    issues = validate_element(update_schema, element, 'insert')
    assert paths(issues) == ['Objects.KnSubjectLink.Element[1].Fields.ToPE']


def test_unknown_or_malformed_nested_object(update_schema: dict[str, Any]) -> None:
    """Unknown object names and nodes without an Element are reported at the object path."""
    element = {'Objects': {'Bogus': {'Element': {}}, 'KnSubjectLink': {'Fields': {}}}}
    issues = validate_element(update_schema, element, 'update')
    assert paths(issues) == ['Objects.Bogus', 'Objects.KnSubjectLink']


def test_element_list_is_validated_per_item(update_schema: dict[str, Any]) -> None:
    """Multiple records in one call are checked individually with an index in the path."""
    issues = validate_element(update_schema, [{'Fields': {'StId': 1, 'Ds': 'a'}}, {'Fields': {'Ds': 'b'}}], 'insert')
    assert paths(issues) == ['[1].Fields.StId']


def test_element_must_be_an_object(update_schema: dict[str, Any]) -> None:
    """A scalar payload is rejected with one clear issue."""
    issues = validate_element(update_schema, 'nope', 'insert')
    assert paths(issues) == ['Element']


def test_objects_list_entries_must_be_mappings(update_schema: dict[str, Any]) -> None:
    """A stray scalar inside the Objects list is reported at the Objects path."""
    issues = validate_element(update_schema, {'Objects': ['garbage']}, 'update')
    assert paths(issues) == ['Objects']
    assert issues[0].message == 'entries must be objects mapping an object name to its Element'
