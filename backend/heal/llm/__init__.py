"""Model selection: one catalogue, chosen by id, swappable by config."""
from heal.llm.models import ModelSpec
from heal.llm.registry import all_models
from heal.llm.registry import available_models
from heal.llm.registry import classifier_model
from heal.llm.registry import default_model
from heal.llm.registry import get_model
from heal.llm.service import get_classifier_llm
from heal.llm.service import get_llm
from heal.llm.service import to_provider_messages

__all__ = [
    "ModelSpec",
    "all_models",
    "available_models",
    "classifier_model",
    "default_model",
    "get_model",
    "get_llm",
    "get_classifier_llm",
    "to_provider_messages",
]
