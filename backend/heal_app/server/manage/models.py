from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import field_validator
from pydantic import model_validator

from heal_app.auth.schemas import UserRole
from heal_app.configs.constants import AuthType
from heal_app.danswerbot.slack.config import VALID_SLACK_FILTERS
from heal_app.db.models import AllowedAnswerFilters
from heal_app.db.models import ChannelConfig
from heal_app.server.features.persona.models import PersonaSnapshot


class VersionResponse(BaseModel):
    backend_version: str


class AuthTypeResponse(BaseModel):
    auth_type: AuthType
    # specifies whether the current auth setup requires
    # users to have verified emails
    requires_verification: bool


class UserInfo(BaseModel):
    id: str
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    role: UserRole
    admin_verified: bool = False
    chat_blocked: bool = False
    # Why the access policy refuses this account right now, or null; the
    # chat screen shows it instead of failing request by request.
    access_blocked_reason: str | None = None


class UserByEmail(BaseModel):
    user_email: str


class UserRoleResponse(BaseModel):
    role: str


class BoostDoc(BaseModel):
    document_id: str
    semantic_id: str
    link: str
    boost: int
    hidden: bool


class BoostUpdateRequest(BaseModel):
    document_id: str
    boost: int


class HiddenUpdateRequest(BaseModel):
    document_id: str
    hidden: bool


class SlackBotTokens(BaseModel):
    bot_token: str
    app_token: str

    model_config = ConfigDict(frozen=True)


class SlackBotConfigCreationRequest(BaseModel):
    # currently, a persona is created for each slack bot config
    # in the future, `document_sets` will probably be replaced
    # by an optional `PersonaSnapshot` object. Keeping it like this
    # for now for simplicity / speed of development
    document_sets: list[int] | None = None
    persona_id: int | None = None  # NOTE: only one of `document_sets` / `persona_id` should be set
    channel_names: list[str]
    respond_tag_only: bool = False
    # If no team members, assume respond in the channel to everyone
    respond_team_member_list: list[str] = []
    answer_filters: list[AllowedAnswerFilters] = []
    # list of user emails
    follow_up_tags: list[str] | None = None

    @field_validator("answer_filters", mode="before")
    @classmethod
    def validate_filters(cls, value: list[str]) -> list[str]:
        if any(test not in VALID_SLACK_FILTERS for test in value):
            raise ValueError(
                f"Slack Answer filters must be one of {VALID_SLACK_FILTERS}"
            )
        return value

    @model_validator(mode="after")
    def validate_document_sets_and_persona_id(
        self,
    ) -> "SlackBotConfigCreationRequest":
        if self.document_sets and self.persona_id:
            raise ValueError("Only one of `document_sets` / `persona_id` should be set")

        return self


class SlackBotConfig(BaseModel):
    id: int
    persona: PersonaSnapshot | None = None
    channel_config: ChannelConfig
