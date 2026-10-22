from pydantic import BaseModel

from heal_app.db.models import DocumentSet as DocumentSetDBModel
from heal_app.db.models import Persona
from heal_app.search.models import RecencyBiasSetting
from heal_app.server.features.prompt.models import PromptSnapshot


class DocumentSet(BaseModel):
    """Document set as it appears on a persona.

    Defined here rather than imported from `server/features/document_set/`,
    which moved to `deprecated/` with the document-set admin. The original
    carried a `cc_pair_descriptors` field built from connector and credential
    snapshots -- types that went with the connectors -- so importing it now
    breaks the API boot.

    Heal has one approved library and no document sets (D3), so
    `PersonaSnapshot.document_sets` is always empty and these fields never
    reach the wire. The model is kept, rather than the field dropped, because
    `web/src/app/chat/ChatIntro.tsx` reads `.document_sets.length` and would
    throw on `undefined` -- the Week 1 rule is that the frontend contract does
    not change.

    Re-home this with the other shared types when the neutral-module step of
    the plan lands; it is a symptom of the same entanglement.
    """

    id: int
    name: str
    description: str
    is_up_to_date: bool
    contains_non_public: bool

    @classmethod
    def from_model(cls, document_set_model: DocumentSetDBModel) -> "DocumentSet":
        return cls(
            id=document_set_model.id,
            name=document_set_model.name,
            description=document_set_model.description,
            contains_non_public=any(
                not cc_pair.is_public
                for cc_pair in document_set_model.connector_credential_pairs
            ),
            is_up_to_date=document_set_model.is_up_to_date,
        )


class CreatePersonaRequest(BaseModel):
    name: str
    description: str
    shared: bool
    num_chunks: float
    llm_relevance_filter: bool
    llm_filter_extraction: bool
    recency_bias: RecencyBiasSetting
    prompt_ids: list[int]
    document_set_ids: list[int]
    llm_model_version_override: str | None = None


class PersonaSnapshot(BaseModel):
    id: int
    name: str
    shared: bool
    is_visible: bool
    display_priority: int | None
    description: str
    num_chunks: float | None
    llm_relevance_filter: bool
    llm_filter_extraction: bool
    llm_model_version_override: str | None
    default_persona: bool
    prompts: list[PromptSnapshot]
    document_sets: list[DocumentSet]

    @classmethod
    def from_model(cls, persona: Persona) -> "PersonaSnapshot":
        if persona.deleted:
            raise ValueError("Persona has been deleted")

        return PersonaSnapshot(
            id=persona.id,
            name=persona.name,
            shared=persona.user_id is None,
            is_visible=persona.is_visible,
            display_priority=persona.display_priority,
            description=persona.description,
            num_chunks=persona.num_chunks,
            llm_relevance_filter=persona.llm_relevance_filter,
            llm_filter_extraction=persona.llm_filter_extraction,
            llm_model_version_override=persona.llm_model_version_override,
            default_persona=persona.default_persona,
            prompts=[PromptSnapshot.from_model(prompt) for prompt in persona.prompts],
            document_sets=[
                DocumentSet.from_model(document_set_model)
                for document_set_model in persona.document_sets
            ],
        )


class PromptTemplateResponse(BaseModel):
    final_prompt_template: str
