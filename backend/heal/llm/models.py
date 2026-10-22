"""What Heal knows about a chat model.

A catalogue entry, not a client. It describes a model well enough for the admin
UI to list it and for the agent to pick one, without any provider SDK being
imported.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """One selectable model."""

    # Stable id used in config and stored against a chat message.
    id: str
    # Shown in the admin UI.
    display_name: str
    # Provider key understood by the LLM factory: "openai", "anthropic", ...
    provider: str
    # Provider-side model name, which may differ from `id`.
    model_name: str
    # Rough input budget, used to decide how much history to keep.
    context_tokens: int
    # False for models kept for comparison but not offered to users.
    selectable: bool = True
    notes: str = ""
    # Set for an OpenAI-compatible endpoint we host ourselves. When present the
    # client talks to this address instead of the provider's own, and the
    # provider name only decides which wire format is spoken.
    base_url: str | None = None

    @property
    def api_key_env(self) -> str:
        """Environment variable that must be set for this provider to work."""
        return f"{self.provider.upper()}_API_KEY"

    @property
    def self_hosted(self) -> bool:
        """Whether this model runs on our own infrastructure."""
        return self.base_url is not None
