# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Upgrade from an older schema: `migrate` runs the system checks before it applies a migration, so the checks
must tolerate a schema older than the models and an agreements app that is not migrated yet."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = "django_stock_alerts"
FIRST = [(APP, "0001_initial")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def leaf():
    return MigrationExecutor(connection).loader.graph.leaf_nodes(APP)


@pytest.fixture
def first_schema(transactional_db):
    """The schema of migration 0001 with one waiting request in a channel that has no URL templates."""
    apps = migrate(FIRST)
    apps.get_model(APP, "Subscription").objects.create(
        channel_idx="no-templates",
        sku="SKU-1",
        email="anna@example.test",
        language="pl",
        consent_at="2026-11-01T10:00:00Z",
        consent_text="I agree",
    )
    yield
    migrate(leaf())


def test_checks_on_the_old_schema_do_not_crash(first_schema):
    call_command("check", databases=["default"])


def test_migrate_to_head_keeps_the_request(first_schema):
    call_command("migrate", verbosity=0)

    apps = MigrationExecutor(connection).loader.project_state(leaf()).apps
    subscription = apps.get_model(APP, "Subscription").objects.get()
    assert (subscription.sku, subscription.status, subscription.wave_claimed_at) == ("SKU-1", "waiting", None)
