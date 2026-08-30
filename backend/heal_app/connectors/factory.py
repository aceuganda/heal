from typing import Any
from typing import Type

from heal_app.configs.constants import DocumentSource
from heal_app.connectors.bookstack.connector import BookstackConnector
from heal_app.connectors.confluence.connector import ConfluenceConnector
from heal_app.connectors.danswer_jira.connector import JiraConnector
from heal_app.connectors.document360.connector import Document360Connector
from heal_app.connectors.file.connector import LocalFileConnector
from heal_app.connectors.github.connector import GithubConnector
from heal_app.connectors.gitlab.connector import GitlabConnector
from heal_app.connectors.gmail.connector import GmailConnector
from heal_app.connectors.gong.connector import GongConnector
from heal_app.connectors.google_drive.connector import GoogleDriveConnector
from heal_app.connectors.google_site.connector import GoogleSitesConnector
from heal_app.connectors.guru.connector import GuruConnector
from heal_app.connectors.hubspot.connector import HubSpotConnector
from heal_app.connectors.interfaces import BaseConnector
from heal_app.connectors.interfaces import EventConnector
from heal_app.connectors.interfaces import LoadConnector
from heal_app.connectors.interfaces import PollConnector
from heal_app.connectors.linear.connector import LinearConnector
from heal_app.connectors.loopio.connector import LoopioConnector
from heal_app.connectors.models import InputType
from heal_app.connectors.notion.connector import NotionConnector
from heal_app.connectors.productboard.connector import ProductboardConnector
from heal_app.connectors.requesttracker.connector import RequestTrackerConnector
from heal_app.connectors.slab.connector import SlabConnector
from heal_app.connectors.slack.connector import SlackLoadConnector
from heal_app.connectors.slack.connector import SlackPollConnector
from heal_app.connectors.web.connector import WebConnector
from heal_app.connectors.zendesk.connector import ZendeskConnector
from heal_app.connectors.zulip.connector import ZulipConnector


class ConnectorMissingException(Exception):
    pass


def identify_connector_class(
    source: DocumentSource,
    input_type: InputType | None = None,
) -> Type[BaseConnector]:
    connector_map = {
        DocumentSource.WEB: WebConnector,
        DocumentSource.FILE: LocalFileConnector,
        DocumentSource.SLACK: {
            InputType.LOAD_STATE: SlackLoadConnector,
            InputType.POLL: SlackPollConnector,
        },
        DocumentSource.GITHUB: GithubConnector,
        DocumentSource.GMAIL: GmailConnector,
        DocumentSource.GITLAB: GitlabConnector,
        DocumentSource.GOOGLE_DRIVE: GoogleDriveConnector,
        DocumentSource.BOOKSTACK: BookstackConnector,
        DocumentSource.CONFLUENCE: ConfluenceConnector,
        DocumentSource.JIRA: JiraConnector,
        DocumentSource.PRODUCTBOARD: ProductboardConnector,
        DocumentSource.SLAB: SlabConnector,
        DocumentSource.NOTION: NotionConnector,
        DocumentSource.ZULIP: ZulipConnector,
        DocumentSource.REQUESTTRACKER: RequestTrackerConnector,
        DocumentSource.GURU: GuruConnector,
        DocumentSource.LINEAR: LinearConnector,
        DocumentSource.HUBSPOT: HubSpotConnector,
        DocumentSource.DOCUMENT360: Document360Connector,
        DocumentSource.GONG: GongConnector,
        DocumentSource.GOOGLE_SITES: GoogleSitesConnector,
        DocumentSource.ZENDESK: ZendeskConnector,
        DocumentSource.LOOPIO: LoopioConnector,
    }
    connector_by_source = connector_map.get(source, {})

    if isinstance(connector_by_source, dict):
        if input_type is None:
            # If not specified, default to most exhaustive update
            connector = connector_by_source.get(InputType.LOAD_STATE)
        else:
            connector = connector_by_source.get(input_type)
    else:
        connector = connector_by_source
    if connector is None:
        raise ConnectorMissingException(f"Connector not found for source={source}")

    if any(
        [
            input_type == InputType.LOAD_STATE
            and not issubclass(connector, LoadConnector),
            input_type == InputType.POLL and not issubclass(connector, PollConnector),
            input_type == InputType.EVENT and not issubclass(connector, EventConnector),
        ]
    ):
        raise ConnectorMissingException(
            f"Connector for source={source} does not accept input_type={input_type}"
        )

    return connector


def instantiate_connector(
    source: DocumentSource,
    input_type: InputType,
    connector_specific_config: dict[str, Any],
    credentials: dict[str, Any],
) -> tuple[BaseConnector, dict[str, Any] | None]:
    connector_class = identify_connector_class(source, input_type)
    connector = connector_class(**connector_specific_config)
    new_credentials = connector.load_credentials(credentials)

    return connector, new_credentials
