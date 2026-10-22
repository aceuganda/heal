import abc
from collections.abc import Callable

from heal_app.chat.models import AnswerQuestionStreamReturn
from heal_app.chat.models import LLMMetricsContainer
from heal_app.indexing.models import InferenceChunk


class QAModel:
    @abc.abstractmethod
    def build_prompt(
        self,
        query: str,
        history_str: str,
        context_chunks: list[InferenceChunk],
    ) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def answer_question_stream(
        self,
        prompt: str,
        llm_context_docs: list[InferenceChunk],
        metrics_callback: Callable[[LLMMetricsContainer], None] | None = None,
    ) -> AnswerQuestionStreamReturn:
        raise NotImplementedError
