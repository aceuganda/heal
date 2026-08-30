"""Tests for how retrieved passages reach the model."""
from heal.chat.prompt_builder import PromptBuilder


class TestNumberedContext:
    def test_passages_are_numbered_for_citation(self) -> None:
        builder = PromptBuilder(
            knowledge_enabled=True,
            context=["First passage.", "Second passage."],
            context_labels=["Guideline A", "Guideline B"],
        )
        _, text = builder.system_message()
        assert "[1] Guideline A" in text
        assert "[2] Guideline B" in text

    def test_the_model_is_told_not_to_invent_citation_numbers(self) -> None:
        """A marker pointing at nothing is worse than no marker."""
        builder = PromptBuilder(knowledge_enabled=True, context=["Passage."])
        _, text = builder.system_message()
        assert "never invent" in text.lower()

    def test_the_model_is_told_to_say_so_rather_than_fill_the_gap(self) -> None:
        builder = PromptBuilder(knowledge_enabled=True, context=["Passage."])
        _, text = builder.system_message()
        assert "say so" in text.lower()

    def test_missing_labels_fall_back_rather_than_crashing(self) -> None:
        builder = PromptBuilder(
            knowledge_enabled=True, context=["A.", "B."], context_labels=["Only one"]
        )
        _, text = builder.system_message()
        assert "[2] Source 2" in text

    def test_no_context_block_when_nothing_was_retrieved(self) -> None:
        _, text = PromptBuilder(knowledge_enabled=True).system_message()
        assert "Approved source material" not in text

    def test_context_survives_history_trimming(self) -> None:
        """The safety instruction and sources must outlive a long conversation."""
        builder = PromptBuilder(
            knowledge_enabled=True,
            context=["Critical passage."],
            history=[(i % 2 == 0, f"turn {i}") for i in range(40)],
        )
        messages = builder.build("current question")
        assert "Critical passage." in messages[0][1]
        assert messages[-1] == ("user", "current question")
