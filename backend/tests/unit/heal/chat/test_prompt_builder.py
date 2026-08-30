"""Tests for prompt assembly."""
from heal.chat.prompt_builder import PromptBuilder
from heal.safety import NO_KNOWLEDGE_BASE_NOTICE


class TestSystemMessage:
    def test_says_there_is_no_document_library_when_knowledge_is_off(self) -> None:
        """Phase 1 must not let the model imply a grounding it does not have."""
        role, text = PromptBuilder(knowledge_enabled=False).system_message()
        assert role == "system"
        assert NO_KNOWLEDGE_BASE_NOTICE.strip() in text

    def test_omits_the_notice_when_knowledge_is_on(self) -> None:
        _, text = PromptBuilder(knowledge_enabled=True).system_message()
        assert NO_KNOWLEDGE_BASE_NOTICE.strip() not in text

    def test_route_instruction_is_appended(self) -> None:
        _, text = PromptBuilder(
            route_instruction="Lead with the dose."
        ).system_message()
        assert "Lead with the dose." in text

    def test_context_is_included_when_present(self) -> None:
        _, text = PromptBuilder(
            knowledge_enabled=True, context=["Give 500mg twice daily."]
        ).system_message()
        assert "Give 500mg twice daily." in text

    def test_no_context_section_when_empty(self) -> None:
        _, text = PromptBuilder(knowledge_enabled=True, context=[]).system_message()
        assert "Approved source material" not in text


class TestHistory:
    def test_roles_alternate_correctly(self) -> None:
        builder = PromptBuilder(history=[(True, "hello"), (False, "hi there")])
        assert builder.history_messages() == [
            ("user", "hello"),
            ("assistant", "hi there"),
        ]

    def test_blank_turns_are_dropped(self) -> None:
        builder = PromptBuilder(history=[(True, "  "), (False, ""), (True, "real")])
        assert builder.history_messages() == [("user", "real")]

    def test_trimmed_from_the_oldest_end(self) -> None:
        """The live question must survive a long conversation, not the oldest turn."""
        history = [(True, f"turn {i}") for i in range(20)]
        messages = PromptBuilder(
            history=history, max_history_messages=4
        ).history_messages()
        assert len(messages) == 4
        assert messages[-1] == ("user", "turn 19")


class TestBuild:
    def test_order_is_system_history_then_message(self) -> None:
        messages = PromptBuilder(history=[(True, "earlier")]).build("what dose?")
        assert [role for role, _ in messages] == ["system", "user", "user"]
        assert messages[-1] == ("user", "what dose?")

    def test_system_message_survives_a_full_history(self) -> None:
        history = [(True, f"t{i}") for i in range(50)]
        messages = PromptBuilder(history=history, max_history_messages=2).build("now")
        assert messages[0][0] == "system"
        assert len(messages) == 4
