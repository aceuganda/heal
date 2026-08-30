"""Assembling the messages sent to the model.

Borrowed in shape from Onyx's `chat/prompt_builder/`, which is the one part of
that codebase worth taking: it turns prompt assembly from inline branches inside
a 543-line function into something with inputs, an output and a test.

What is deliberately NOT borrowed is Onyx's tool loop. Nothing here lets the
model choose an action.
"""
from dataclasses import dataclass
from dataclasses import field
from typing import Literal

from heal.safety import build_safety_instruction

Role = Literal["system", "user", "assistant"]
# A provider-neutral message. Converted to the client's own message type at the
# LLM boundary (heal/llm/service.py), so nothing else needs that dependency.
Message = tuple[Role, str]


@dataclass
class PromptBuilder:
    """Builds the message list for one chat turn.

    Order is fixed and meaningful: safety instruction, then route instruction,
    then history oldest-first, then the current message. History is trimmed from
    the oldest end so the safety instruction and the live question always
    survive a long conversation.
    """

    knowledge_enabled: bool = False
    # Extra instruction from the route table for this intent.
    route_instruction: str = ""
    # Prior turns as (is_user, text), oldest first.
    history: list[tuple[bool, str]] = field(default_factory=list)
    # Approved context passages, in citation order. Index in this list is the
    # citation number the model is told to use, so order is meaningful.
    context: list[str] = field(default_factory=list)
    # Labels parallel to `context`, one per passage. When present, passages are
    # numbered and the model is instructed to cite by number.
    context_labels: list[str] = field(default_factory=list)
    max_history_messages: int = 10

    def system_message(self) -> Message:
        parts = [build_safety_instruction(self.knowledge_enabled)]
        if self.route_instruction:
            parts.append(f"\nFor this message specifically:\n{self.route_instruction}")
        if self.context:
            parts.append(self._context_block())
        return ("system", "".join(parts))

    def _context_block(self) -> str:
        """Approved passages, numbered so the model can cite them.

        Numbering is explicit rather than left to the model: a citation that
        points at nothing is worse than no citation, because the marker itself
        implies a source was checked.
        """
        passages = []
        for i, text in enumerate(self.context, start=1):
            label = (
                self.context_labels[i - 1]
                if i - 1 < len(self.context_labels)
                else f"Source {i}"
            )
            passages.append(f"[{i}] {label}\n{text}")
        return (
            "\nApproved source material, numbered. Use it in preference to your "
            "own recollection. Cite the number in square brackets immediately "
            "after each claim it supports, like [1]. Cite only these numbers, "
            "and never invent one. If these passages do not answer the "
            "question, say so plainly rather than filling the gap from memory."
            "\n\n" + "\n\n---\n\n".join(passages)
        )

    def history_messages(self) -> list[Message]:
        """Recent turns, trimmed from the oldest end."""
        recent = [(is_user, t) for is_user, t in self.history if t and t.strip()]
        recent = recent[-self.max_history_messages :]
        return [("user" if is_user else "assistant", text) for is_user, text in recent]

    def build(self, message: str) -> list[Message]:
        """The full message list for this turn."""
        return [
            self.system_message(),
            *self.history_messages(),
            ("user", message),
        ]
