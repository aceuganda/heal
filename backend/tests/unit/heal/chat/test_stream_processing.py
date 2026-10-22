"""Tests for the token stream processor."""
from heal.chat.stream_processing import StreamProcessor


class TestStreamProcessor:
    def test_passes_tokens_through_in_order(self) -> None:
        p = StreamProcessor()
        assert list(p.process(["one ", "two ", "three"])) == ["one ", "two ", "three"]

    def test_accumulates_exactly_what_was_yielded(self) -> None:
        """The stored answer must equal what the user saw, character for character."""
        p = StreamProcessor()
        emitted = list(p.process(["500", "mg ", "BD"]))
        assert p.text == "".join(emitted)

    def test_prefix_is_emitted_before_the_first_token(self) -> None:
        p = StreamProcessor(prefix="CALL 912 NOW. ")
        out = list(p.process(["then ", "do this"]))
        assert out[0] == "CALL 912 NOW. "
        assert p.text.startswith("CALL 912 NOW. ")

    def test_prefix_survives_an_empty_stream(self) -> None:
        """Escalation copy must reach the user even if generation produces nothing."""
        p = StreamProcessor(prefix="CALL 912 NOW. ")
        assert list(p.process([])) == ["CALL 912 NOW. "]
        assert p.text == "CALL 912 NOW. "

    def test_empty_tokens_are_skipped(self) -> None:
        p = StreamProcessor()
        assert list(p.process(["a", "", None or "", "b"])) == ["a", "b"]

    def test_no_prefix_yields_nothing_extra(self) -> None:
        p = StreamProcessor()
        assert list(p.process([])) == []
        assert p.text == ""
