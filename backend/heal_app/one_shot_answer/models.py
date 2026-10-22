from pydantic import BaseModel
from pydantic import model_validator

from heal_app.chat.models import DanswerQuotes
from heal_app.chat.models import QADocsResponse
from heal_app.configs.constants import MessageType
from heal_app.search.models import RetrievalDetails


class QueryRephrase(BaseModel):
    rephrased_query: str


class ThreadMessage(BaseModel):
    message: str
    sender: str | None = None
    role: MessageType


class DirectQARequest(BaseModel):
    messages: list[ThreadMessage]
    prompt_id: int | None = None
    persona_id: int
    retrieval_options: RetrievalDetails
    chain_of_thought: bool = False

    @model_validator(mode="after")
    def check_chain_of_thought_and_prompt_id(self) -> "DirectQARequest":
        if self.chain_of_thought and self.prompt_id is not None:
            raise ValueError(
                "If chain_of_thought is True, prompt_id must be None"
                "The chain of thought prompt is only for question "
                "answering and does not accept customizing."
            )

        return self


class OneShotQAResponse(BaseModel):
    # This is built piece by piece, any of these can be None as the flow could break
    answer: str | None = None
    rephrase: str | None = None
    quotes: DanswerQuotes | None = None
    docs: QADocsResponse | None = None
    llm_chunks_indices: list[int] | None = None
    error_msg: str | None = None
    answer_valid: bool = True  # Reflexion result, default True if Reflexion not run
    chat_message_id: int | None = None
