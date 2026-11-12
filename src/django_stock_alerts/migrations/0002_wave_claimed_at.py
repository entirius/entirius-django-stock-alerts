# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_stock_alerts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="wave_claimed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Set when a restock wave enqueued the alert; a fresh claim is not taken again",
                null=True,
            ),
        ),
    ]
