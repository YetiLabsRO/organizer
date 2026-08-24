"""Schema authoring, provisioning, and drift."""

from django.test import TestCase

from integrations.notion import schema
from integrations.notion.exceptions import NotionSchemaDriftError
from integrations.notion.tests.helpers import ALL_PROPERTIES, make_connection, make_fake, make_user, property_titles
from tasks.models import Project, Tag, TaskItem


def data_source_from(titles):
    return {"id": "ds-1", "properties": {title: {"id": pid, "type": "rich_text"} for title, pid in titles.items()}}


class SchemaShapeTests(TestCase):
    def test_initial_schema_omits_the_self_relation(self):
        # The relation points at a data source that does not exist until create_database returns.
        properties = schema.initial_properties()

        self.assertNotIn(schema.PARENT_TASK, properties)
        self.assertIn(schema.TITLE, properties)
        self.assertEqual(list(properties[schema.TITLE]), ["title"])

    def test_self_relation_points_at_its_own_data_source(self):
        relation = schema.self_relation_property("ds-9")[schema.PARENT_TASK]["relation"]

        self.assertEqual(relation["data_source_id"], "ds-9")
        self.assertEqual(relation["type"], "single_property")

    def test_status_and_completion_are_separate_properties(self):
        # Organizer's status and completed are independent, so collapsing them into Notion's
        # single `status` type would be lossy.
        properties = schema.initial_properties()

        self.assertIn("select", properties[schema.STATUS])
        self.assertIn("checkbox", properties[schema.DONE])

    def test_start_and_deadline_are_separate_dates(self):
        # A Notion date range cannot express an end without a start, and Organizer routinely has a
        # deadline with no start date.
        properties = schema.initial_properties()

        self.assertIn("date", properties[schema.START])
        self.assertIn("date", properties[schema.DEADLINE])

    def test_status_options_use_the_labels_the_app_shows(self):
        options = schema.initial_properties()[schema.STATUS]["select"]["options"]
        names = [option["name"] for option in options]

        self.assertEqual(names, [label for _, label in TaskItem.TAKSITEM_STATUSES])


class ColorTests(TestCase):
    def test_hex_colors_land_on_notions_palette(self):
        self.assertEqual(schema.nearest_notion_color("#d44c47"), "red")
        self.assertEqual(schema.nearest_notion_color("#337ea9"), "blue")
        self.assertEqual(schema.nearest_notion_color("#448361"), "green")

    def test_the_model_default_white_stays_default(self):
        # Tag.color defaults to #FFFFFF, which means "no colour chosen", not "white".
        self.assertEqual(schema.nearest_notion_color("#FFFFFF"), "default")

    def test_malformed_colors_fall_back(self):
        self.assertEqual(schema.nearest_notion_color(""), "default")
        self.assertEqual(schema.nearest_notion_color("nonsense"), "default")

    def test_shorthand_hex_is_understood(self):
        self.assertEqual(schema.nearest_notion_color("#f00"), "red")


class DriftTests(TestCase):
    def setUp(self):
        self.titles = property_titles()
        self.property_ids = dict(self.titles)

    def test_unchanged_schema_passes(self):
        self.assertTrue(schema.check_drift(data_source_from(self.titles), self.property_ids))

    def test_a_renamed_property_is_not_drift(self):
        renamed = dict(self.titles)
        renamed["Termen limită"] = renamed.pop(schema.DEADLINE)

        self.assertTrue(schema.check_drift(data_source_from(renamed), self.property_ids))

        # ...and writing follows the rename, because properties are addressed by id.
        names = schema.resolve_property_names(data_source_from(renamed), self.property_ids)
        self.assertEqual(names[schema.DEADLINE], "Termen limită")

    def test_a_deleted_property_is_drift(self):
        without_deadline = {title: pid for title, pid in self.titles.items() if title != schema.DEADLINE}

        with self.assertRaises(NotionSchemaDriftError) as caught:
            schema.check_drift(data_source_from(without_deadline), self.property_ids)
        self.assertIn(schema.DEADLINE, str(caught.exception))

    def test_losing_the_cosmetic_property_is_not_drift(self):
        # `Last edited by` is for the user's benefit; echo suppression reads the page's own metadata.
        without_editor = {title: pid for title, pid in self.titles.items() if title != schema.LAST_EDITED_BY}

        self.assertTrue(schema.check_drift(data_source_from(without_editor), self.property_ids))


class ProvisionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.connection = make_connection(self.user)
        self.fake = make_fake()

    def test_creates_the_database_then_patches_the_relation_in(self):
        database = schema.provision(self.fake, self.connection, "parent-page")

        calls = [name for name, _ in self.fake.calls]
        self.assertEqual(calls[0], "create_database")
        # The self-relation and the option seeding can only happen after the data source exists.
        self.assertEqual(calls.count("update_data_source"), 2)

        self.assertEqual(database.data_source_id, "ds-1")
        self.assertEqual(database.parent_page_id, "parent-page")
        self.assertEqual(set(database.property_ids), set(ALL_PROPERTIES))

    def test_seeded_options_come_from_the_users_own_projects_and_tags(self):
        project = Project.objects.create(title="Home")
        tag = Tag.objects.create(name="errand", color="#d44c47")
        other_user = make_user("someone-else")
        other_project = Project.objects.create(title="Not mine")
        TaskItem.objects.create(owner=self.user, title="mine", project=project).tags.add(tag)
        TaskItem.objects.create(owner=other_user, title="theirs", project=other_project)

        seeds = schema.option_seed_properties(self.user)

        project_names = [option["name"] for option in seeds[schema.PROJECT]["select"]["options"]]
        self.assertEqual(project_names, ["Home"])
        tag_options = seeds[schema.TAGS]["multi_select"]["options"]
        self.assertEqual(tag_options[0]["name"], "errand")
        self.assertEqual(tag_options[0]["color"], "red")

    def test_option_names_never_contain_commas(self):
        # Notion rejects commas in select option names outright.
        Project.objects.create(title="Home, sweet home")
        TaskItem.objects.create(owner=self.user, title="t", project=Project.objects.first())

        seeds = schema.option_seed_properties(self.user)
        names = [option["name"] for option in seeds[schema.PROJECT]["select"]["options"]]

        self.assertTrue(all("," not in name for name in names))
