"""Live chat must retrieve and expose ranked passages before generating."""
import json
from types import SimpleNamespace
from uuid import uuid4

from heal.chat import message_flow
from heal.knowledge.models import Chunk, RetrievedChunk, SourceRef
from heal.knowledge.store import QdrantKnowledgeStore
from heal.llm import defaults
from heal.llm.service import Generation
from heal.medical_guidance import agent as agent_mod
from heal.medical_guidance.agent import MedicalGuidanceAgent
from heal.medical_guidance.routes import MedicalIntent
from heal.medical_guidance.understanding import Understanding


def test_chat_searches_using_saved_hybrid_settings_before_streaming(monkeypatch):
    steps = []
    selected = RetrievedChunk(
        chunk=Chunk(
            chunk_id="approved",
            text="Approved clinical guidance for malaria.",
            source=SourceRef(source_id="guideline", title="Malaria guideline"),
        ),
        score=0.9,
        dense_score=0.8,
        sparse_score=0.7,
    )
    rejected = RetrievedChunk(
        chunk=Chunk(
            chunk_id="weak",
            text="Weak irrelevant passage.",
            source=SourceRef(source_id="other", title="Other guideline"),
        ),
        score=0.1,
    )
    monkeypatch.setattr(defaults, "stored", lambda refresh=False: {
        "hybrid_search": True, "hybrid_alpha": 0.4, "min_retrieval_score": 0.5,
    })
    monkeypatch.setattr(agent_mod, "understand", lambda *a, **kw: Understanding(
        intent=MedicalIntent.CLINICAL_QUESTION,
        query="malaria diagnosis", original="malaria?", classified=True,
    ))
    store = QdrantKnowledgeStore()

    def candidates(query, lexical_query, settings):
        steps.append("retrieve")
        assert query == "malaria diagnosis"
        assert "malaria?" in lexical_query
        assert settings.hybrid_search is True
        assert settings.alpha == 0.4
        return [selected, rejected]

    monkeypatch.setattr(store, "candidates", candidates)
    agent = MedicalGuidanceAgent(knowledge_enabled=True, store=store)
    monkeypatch.setattr(message_flow, "MedicalGuidanceAgent", lambda: agent)
    monkeypatch.setattr(agent_mod.audit, "emit", lambda event: None)

    def generate(model_id, prompt, **kwargs):
        steps.append("generate")
        assert selected.text in prompt[0][1]
        assert rejected.text not in prompt[0][1]
        return iter(["Grounded answer [1]."]), Generation(model_id="gpt-4o-mini")

    monkeypatch.setattr(agent_mod, "stream_with_failover", generate)
    monkeypatch.setattr(message_flow, "get_language_service", lambda: SimpleNamespace(
        is_luganda=lambda language: False,
    ))
    monkeypatch.setattr(message_flow, "get_chat_session_by_id", lambda **kw: None)
    monkeypatch.setattr(message_flow, "get_default_llm_token_encode", lambda: list)
    root = SimpleNamespace(id=0)
    monkeypatch.setattr(message_flow, "get_or_create_root_message", lambda **kw: root)
    saved = []

    def save(**kwargs):
        saved.append(kwargs)
        return SimpleNamespace(id=len(saved))

    monkeypatch.setattr(message_flow, "create_new_chat_message", save)
    monkeypatch.setattr(message_flow, "create_chat_chain", lambda **kw: (
        SimpleNamespace(id=1), [],
    ))
    monkeypatch.setattr(message_flow, "build_citations", lambda **kw: ([], {}))
    monkeypatch.setattr(message_flow, "translate_db_message_to_chat_message_detail",
                        lambda message: SimpleNamespace(model_dump=lambda: {"message_id": 2}))
    request = SimpleNamespace(
        message="malaria?", language="english", chat_session_id=uuid4(),
        parent_message_id=None, prompt_id=None,
    )
    session = SimpleNamespace(commit=lambda: None)
    stream = message_flow.stream_chat_message(request, None, session)

    documents = json.loads(next(stream))
    assert steps == ["retrieve"]
    assert documents["rephrased_query"] == "malaria diagnosis"
    assert len(documents["top_documents"]) == 1
    assert documents["top_documents"][0]["score"] == 0.9
    assert selected.text in documents["top_documents"][0]["match_highlights"]

    packets = [json.loads(packet) for packet in stream]
    assert steps == ["retrieve", "generate"]
    assert packets[0]["answer_piece"] == "Grounded answer [1]."
    assert saved[-1]["rephrased_query"] == "malaria diagnosis"
