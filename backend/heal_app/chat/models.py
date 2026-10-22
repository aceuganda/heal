from collections.abc import Iterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from heal_app.configs.constants import DocumentSource
from heal_app.search.models import QueryFlow
from heal_app.search.models import RetrievalDocs
from heal_app.search.models import SearchResponse
from heal_app.search.models import SearchType


class LlmDoc(BaseModel):
    """This contains the minimal set information for the LLM portion including citations"""

    document_id: str
    content: str
    semantic_identifier: str
    source_type: DocumentSource
    updated_at: datetime | None = None
    link: str | None = None


# First chunk of info for streaming QA
class QADocsResponse(RetrievalDocs):
    rephrased_query: str | None = None
    predicted_flow: QueryFlow | None = None
    predicted_search: SearchType | None = None
    applied_source_filters: list[DocumentSource] | None = None
    applied_time_cutoff: datetime | None = None
    recency_bias_multiplier: float

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        initial_dict = super().model_dump(*args, **kwargs)
        initial_dict["applied_time_cutoff"] = (
            self.applied_time_cutoff.isoformat() if self.applied_time_cutoff else None
        )
        return initial_dict


# Second chunk of info for streaming QA
class LLMRelevanceFilterResponse(BaseModel):
    relevant_chunk_indices: list[int]


class DanswerAnswerPiece(BaseModel):
    # A small piece of a complete answer. Used for streaming back answers.
    answer_piece: str | None = None  # if None, specifies the end of an Answer


# An intermediate representation of citations, later translated into
# a mapping of the citation [n] number to SearchDoc
class CitationInfo(BaseModel):
    citation_num: int
    document_id: str


class StreamingError(BaseModel):
    error: str


class DanswerQuote(BaseModel):
    # This is during inference so everything is a string by this point
    quote: str
    document_id: str
    link: str | None = None
    source_type: str
    semantic_identifier: str
    blurb: str


class DanswerQuotes(BaseModel):
    quotes: list[DanswerQuote]


class DanswerAnswer(BaseModel):
    answer: str | None = None


class QAResponse(SearchResponse, DanswerAnswer):
    quotes: list[DanswerQuote] | None = None
    predicted_flow: QueryFlow
    predicted_search: SearchType
    eval_res_valid: bool | None = None
    llm_chunks_indices: list[int] | None = None
    error_msg: str | None = None


AnswerQuestionReturn = tuple[DanswerAnswer, DanswerQuotes]


AnswerQuestionStreamReturn = Iterator[
    DanswerAnswerPiece | DanswerQuotes | StreamingError
]


class LLMMetricsContainer(BaseModel):
    prompt_tokens: int
    response_tokens: int
