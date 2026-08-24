"""Shared fixtures for the Notion integration tests."""

from django.contrib.auth import get_user_model

from integrations.notion import schema
from integrations.notion.models import NotionConnection, NotionDatabase
from integrations.notion.tests.fakes import BOT_ID, FakeNotion

ALL_PROPERTIES = (*schema.REQUIRED_PROPERTIES, schema.LAST_EDITED_BY)


def make_user(username="tester", **kwargs):
    return get_user_model().objects.create_user(username=username, password="hunter2-not-a-real-password", **kwargs)


def property_titles():
    """Notion property title -> property id, as a freshly provisioned database would look."""
    return {name: f"pid-{index}" for index, name in enumerate(ALL_PROPERTIES)}


def make_connection(user, bot_id=BOT_ID, status=NotionConnection.ACTIVE):
    connection = NotionConnection(user=user, bot_id=bot_id, status=status, workspace_name="Test workspace")
    connection.access_token = "secret-access-token"
    connection.refresh_token = "secret-refresh-token"
    connection.save()
    return connection


def make_database(connection, bootstrapped=True):
    return NotionDatabase.objects.create(
        connection=connection,
        database_id="db-1",
        data_source_id="ds-1",
        parent_page_id="parent-page",
        property_ids={name: f"pid-{index}" for index, name in enumerate(ALL_PROPERTIES)},
        bootstrap_state=NotionDatabase.BOOTSTRAP_DONE if bootstrapped else NotionDatabase.BOOTSTRAP_PENDING,
    )


def make_fake(bot_id=BOT_ID):
    return FakeNotion(bot_id=bot_id, property_titles=property_titles())


def notion_props(fake, **logical_values):
    """Build a write-shaped property payload keyed by the *current* Notion titles."""
    return {logical: value for logical, value in logical_values.items()}
