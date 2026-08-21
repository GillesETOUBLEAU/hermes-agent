"""Tests for _repair_tool_call_arguments — malformed JSON repair pipeline."""

import json

from agent.message_sanitization import tool_args_look_truncated
from run_agent import _repair_tool_call_arguments


class TestRepairToolCallArguments:
    """Verify each repair stage in the pipeline."""

    # -- Stage 1: empty / whitespace-only --

    def test_empty_string_returns_empty_object(self):
        assert _repair_tool_call_arguments("", "t") == "{}"



    # -- Stage 2: Python None literal --



    # -- Stage 3: trailing comma repair --


    def test_trailing_comma_in_array(self):
        result = _repair_tool_call_arguments('{"a": [1, 2,]}', "t")
        parsed = json.loads(result)
        assert parsed == {"a": [1, 2]}


    # -- Stage 4: unclosed brackets --



    # -- Stage 5: excess closing delimiters --



    # -- Stage 6: last resort --


    def test_unrepairable_partial_returns_empty_object(self):
        # Truncated in the middle of a string key — bracket closing won't help
        assert _repair_tool_call_arguments('{"truncated": "val', "t") == "{}"

    # -- Valid JSON passthrough (this path is via except, but still works) --


    # -- Combined repairs --



    # -- Stage 0: strict=False (literal control chars in strings) --
    # llama.cpp backends sometimes emit literal tabs/newlines inside JSON
    # string values. strict=False accepts these; we re-serialise to the
    # canonical wire form (#12068).




    # -- Stage 4: control-char escape fallback --




class TestDeQuotedValueRepair:
    """Stage 5: a string value whose opening quote the provider dropped.

    z-ai/glm-5.2 via OpenRouter spliced its streamed tool-call argument
    chunks one character off at a delta boundary and emitted
    ``"kind": needss_input"`` on 77 consecutive ``kanban_block`` calls. The
    payload is complete — not truncated — so every earlier pass fails and the
    session used to die with a bogus "max output tokens" diagnosis.
    """

    LIVE_PAYLOAD = (
        '{"reason": "Rapport trafic soft-ui prêt à valider. '
        'Fichier livré : report.html (38 KB).", '
        '"kind": needss_input", "board": "wmh"}'
    )

    def test_live_payload_is_repaired(self):
        parsed = json.loads(_repair_tool_call_arguments(self.LIVE_PAYLOAD, "kanban_block"))
        assert parsed["kind"] == "needss_input"
        assert parsed["board"] == "wmh"
        assert parsed["reason"].startswith("Rapport trafic soft-ui")

    def test_both_quotes_dropped(self):
        parsed = json.loads(_repair_tool_call_arguments('{"kind": needs_input}', "t"))
        assert parsed == {"kind": "needs_input"}

    def test_colon_inside_a_string_value_is_not_a_separator(self):
        raw = '{"reason": "note: see the board", "kind": needss_input"}'
        parsed = json.loads(_repair_tool_call_arguments(raw, "t"))
        assert parsed == {"reason": "note: see the board", "kind": "needss_input"}

    def test_escaped_quote_inside_value_survives(self):
        raw = '{"reason": "a: b\\" c", "kind": needss_input"}'
        parsed = json.loads(_repair_tool_call_arguments(raw, "t"))
        assert parsed == {"reason": 'a: b" c', "kind": "needss_input"}

    def test_literals_and_numbers_are_left_alone(self):
        parsed = json.loads(_repair_tool_call_arguments('{"flag": true, "n": 12,}', "t"))
        assert parsed == {"flag": True, "n": 12}

    def test_genuinely_truncated_still_unrepairable(self):
        # The new pass must not rescue a real truncation into bogus JSON.
        assert _repair_tool_call_arguments('{"truncated": "val', "t") == "{}"


class TestToolArgsLookTruncated:
    """Cut off mid-value vs complete-but-corrupt — the two need opposite
    recoveries, so the discriminator is pinned in both directions."""

    def test_unterminated_string_is_truncated(self):
        assert tool_args_look_truncated('{"path": "/etc/ho')

    def test_unclosed_object_is_truncated(self):
        assert tool_args_look_truncated('{"a": 1, "b": {"c": 2}')

    def test_unclosed_array_is_truncated(self):
        assert tool_args_look_truncated('{"xs": [1, 2')

    def test_dangling_separator_is_truncated(self):
        assert tool_args_look_truncated('{"a": 1,')
        assert tool_args_look_truncated('{"a":')

    def test_corrupt_but_closed_is_not_truncated(self):
        # The live glitch: complete payload, invalid JSON.
        assert not tool_args_look_truncated('{"kind": needss_input"}')
        # Missing colon — nothing can repair it, still not a truncation.
        assert not tool_args_look_truncated('{"kind" "needs_input"}')

    def test_valid_json_is_not_truncated(self):
        assert not tool_args_look_truncated('{"kind": "needs_input"}')

    def test_escaped_quote_does_not_fake_an_open_string(self):
        assert not tool_args_look_truncated('{"reason": "say \\"hi\\""}')

    def test_brace_inside_a_string_does_not_count(self):
        assert not tool_args_look_truncated('{"reason": "use { and ["}')

    def test_empty_is_not_truncated(self):
        assert not tool_args_look_truncated("")
        assert not tool_args_look_truncated("   ")

    def test_dropped_quote_that_closes_is_corruption_not_truncation(self):
        # Odd quote count: depth tracking is meaningless past the dropped
        # quote, so a payload that still closes counts as complete.
        assert not tool_args_look_truncated('{"kind": needss_input", "board": "wmh"}')

    def test_nested_truncation_that_happens_to_end_on_a_brace(self):
        assert tool_args_look_truncated('{"a": {"b": 1}')
