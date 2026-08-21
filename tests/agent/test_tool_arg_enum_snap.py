"""Enum snapping at the tool-dispatch boundary.

A provider that mangles an enum value by a single character (z-ai/glm-5.2 via
OpenRouter emitted ``needss_input`` for ``kanban_block(kind=...)``) otherwise
burns a round-trip — or, on a kanban worker, the task's whole retry budget —
on a deterministic glitch. Snapping is deliberately narrow: exactly one schema
value within a single edit, or an exact case-insensitive match.
"""

from types import SimpleNamespace

from agent.tool_executor import (
    _enum_properties_for_tool,
    _one_edit_apart,
    _snap_enum_arguments,
)


KANBAN_BLOCK_TOOL = {
    "type": "function",
    "function": {
        "name": "kanban_block",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["dependency", "needs_input", "capability", "transient"],
                },
            },
        },
    },
}


def _agent(tools=None):
    return SimpleNamespace(tools=tools if tools is not None else [KANBAN_BLOCK_TOOL])


class TestOneEditApart:
    def test_insertion(self):
        assert _one_edit_apart("needss_input", "needs_input")

    def test_deletion(self):
        assert _one_edit_apart("need_input", "needs_input")

    def test_substitution(self):
        assert _one_edit_apart("needt_input", "needs_input")

    def test_identical_is_not_one_edit(self):
        assert not _one_edit_apart("needs_input", "needs_input")

    def test_two_edits_rejected(self):
        assert not _one_edit_apart("neeed_inputt", "needs_input")

    def test_length_gap_rejected(self):
        assert not _one_edit_apart("x", "needs_input")


class TestSnapEnumArguments:
    def test_live_glitch_is_snapped(self):
        args = {"reason": "report ready", "kind": "needss_input"}
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args["kind"] == "needs_input"

    def test_case_drift_is_snapped(self):
        args = {"kind": "NEEDS_INPUT"}
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args["kind"] == "needs_input"

    def test_valid_value_untouched(self):
        args = {"kind": "capability"}
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args["kind"] == "capability"

    def test_ambiguous_value_left_for_the_tool_to_reject(self):
        tool = {
            "type": "function",
            "function": {
                "name": "t",
                "parameters": {
                    "type": "object",
                    "properties": {"mode": {"enum": ["fast", "last"]}},
                },
            },
        }
        args = {"mode": "mast"}
        _snap_enum_arguments(_agent([tool]), "t", args)
        assert args["mode"] == "mast"

    def test_far_value_left_alone(self):
        args = {"kind": "totally-wrong"}
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args["kind"] == "totally-wrong"

    def test_non_enum_parameter_untouched(self):
        args = {"reason": "dependency"}
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args["reason"] == "dependency"

    def test_unknown_tool_is_a_noop(self):
        args = {"kind": "needss_input"}
        _snap_enum_arguments(_agent(), "some_other_tool", args)
        assert args["kind"] == "needss_input"

    def test_empty_args_is_a_noop(self):
        args = {}
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args == {}

    def test_malformed_tool_definitions_do_not_raise(self):
        args = {"kind": "needss_input"}
        _snap_enum_arguments(_agent(["not-a-dict", {"function": None}]), "kanban_block", args)
        assert args["kind"] == "needss_input"

    def test_agent_without_tools_is_a_noop(self):
        args = {"kind": "needss_input"}
        _snap_enum_arguments(SimpleNamespace(), "kanban_block", args)
        assert args["kind"] == "needss_input"


class TestEnumPropertiesForTool:
    def test_collects_only_enum_properties(self):
        assert _enum_properties_for_tool(_agent(), "kanban_block") == {
            "kind": ["dependency", "needs_input", "capability", "transient"]
        }

    def test_unknown_tool_returns_empty(self):
        assert _enum_properties_for_tool(_agent(), "nope") == {}


class TestEndToEndProviderGlitch:
    """Repair + snap together restore the exact call the provider mangled."""

    def test_dequoted_enum_round_trips_to_a_valid_call(self):
        import json

        from agent.message_sanitization import _repair_tool_call_arguments

        wire = (
            '{"reason": "Rapport trafic soft-ui prêt à valider.", '
            '"kind": needss_input", "board": "wmh"}'
        )
        args = json.loads(_repair_tool_call_arguments(wire, "kanban_block"))
        _snap_enum_arguments(_agent(), "kanban_block", args)
        assert args == {
            "reason": "Rapport trafic soft-ui prêt à valider.",
            "kind": "needs_input",
            "board": "wmh",
        }
