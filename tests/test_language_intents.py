"""Test language intents."""
from typing import Any, Dict, Iterable, Set

from hassil import Intents
from hassil.expression import Expression, ListReference, RuleReference, Sequence
from hassil.intents import TextSlotList


def test_language_common(
    language,
    language_sentences_yaml: Dict[str, Any],
):
    """Test the language common file."""
    common_files = [key for key in language_sentences_yaml if key.startswith("_")]

    assert common_files == [
        "_common.yaml"
    ], "Only _common.yaml is allowed as common file"

    if language == "en":
        return

    content = language_sentences_yaml["_common.yaml"]

    if values := content["lists"].get("color", {}).get("values", []):
        for color in values:
            assert isinstance(
                color, dict
            ), "Color list should use the in-out format to output English color names for Home Assistant to consume. See sentences/nl/_common.yaml for an example."

    assert (
        "intents" not in content
    ), "_common.yaml is a common file and should not contain intents"


def test_language_sentences(
    language_sentences: Intents, intent_schemas: Dict[str, Any]
):
    """Ensure all language sentences contain valid slots, lists, rules, etc."""
    # Add placeholder slots that HA will generate
    language_sentences.slot_lists["area"] = TextSlotList(values=[])
    language_sentences.slot_lists["name"] = TextSlotList(values=[])

    # Lint sentences
    for intent_name, intent in language_sentences.intents.items():
        intent_schema = intent_schemas[intent_name]
        slot_schema = intent_schema["slots"]
        slot_combinations = intent_schema.get("slot_combinations")

        for data in intent.data:
            for sentence in data.sentences:
                found_slots: Set[str] = set()
                for expression in _flatten(sentence):
                    _verify(
                        expression,
                        language_sentences,
                        intent_name,
                        slot_schema,
                        visited_rules=set(),
                        found_slots=found_slots,
                    )

                # Check required slots
                for slot_name, slot_info in slot_schema.items():
                    if slot_info.get("required", False):
                        assert (
                            slot_name in found_slots
                        ), f"Missing required slot: '{slot_name}', intent='{intent_name}', sentence='{sentence.text}'"

                if slot_combinations:
                    # Verify one of the combinations is matched
                    combo_matched = False
                    for combo_slots in slot_combinations.values():
                        if set(combo_slots) == found_slots:
                            combo_matched = True
                            break

                    assert (
                        combo_matched
                    ), f"Slot combination not matched: intent='{intent_name}', slots={found_slots}, sentence='{sentence.text}'"


def _verify(
    expression: Expression,
    intents: Intents,
    intent_name: str,
    slot_schema: Dict[str, Any],
    visited_rules: Set[str],
    found_slots: Set[str],
):
    if isinstance(expression, ListReference):
        list_ref: ListReference = expression

        # Ensure list exists
        assert (
            list_ref.list_name in intents.slot_lists
        ), f"Missing slot list: {{{list_ref.list_name}}}. Available slots: {', '.join(intents.slot_lists)}"

        # Ensure slot is part of intent
        assert (
            list_ref.slot_name in slot_schema
        ), f"Unexpected slot '{list_ref.slot_name}' for intent '{intent_name}"

        # Track slots for combination check
        found_slots.add(list_ref.slot_name)
    elif isinstance(expression, RuleReference):
        rule_ref: RuleReference = expression
        assert (
            rule_ref.rule_name in intents.expansion_rules
        ), f"Missing expansion rule: <{rule_ref.rule_name}>"

        # Check for recursive rules (not supported)
        assert (
            rule_ref.rule_name not in visited_rules
        ), f"Recursive rule detected: <{rule_ref.rule_name}>"

        visited_rules.add(rule_ref.rule_name)

        # Verify rule body
        for body_expression in _flatten(intents.expansion_rules[rule_ref.rule_name]):
            _verify(
                body_expression,
                intents,
                intent_name,
                slot_schema,
                visited_rules,
                found_slots,
            )


def _flatten(expression: Expression) -> Iterable[Expression]:
    if isinstance(expression, Sequence):
        seq: Sequence = expression
        for item in seq.items:
            yield from _flatten(item)
    else:
        yield expression
