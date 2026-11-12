# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Standalone test settings: PostgreSQL via DATABASE_URL (zeno `make module-test` passes its own), else a CI default.

`STOCK_ALERTS_TEST_NO_AGREEMENTS=1` leaves django_agreements out: the suite's second run, without the soft dependency.
"""

import os
from importlib.util import find_spec

import dj_database_url

SECRET_KEY = "not so secret test secret for the stock alerts suite"  # noqa: S105 — test-only
DEBUG = True
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "django_regional",
    "django_pim",  # django_matrix models import it
    "django_matrix",
    "django_email",
    "django_stock_alerts",
]
WITH_AGREEMENTS = not os.environ.get("STOCK_ALERTS_TEST_NO_AGREEMENTS")
if WITH_AGREEMENTS:
    INSTALLED_APPS.append("django_agreements")
# django_access when importable (zeno): the key scope and tests/test_access_ownership.py.
if find_spec("django_access"):
    INSTALLED_APPS.append("django_access")
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "tests.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "django_utils.api.v2_errors.v2_exception_handler",
}
SPECTACULAR_SETTINGS = {"TITLE": "django-stock-alerts API v2", "VERSION": "2.0.0", "OAS_VERSION": "3.1.0"}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

DATABASES = {
    "default": dj_database_url.config(default="postgresql://postgres:postgres@localhost:5432/test_stock_alerts")
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

# Required by django_pim and django_accounts settings, imported through django_matrix.
TMP_DIR = "/tmp"  # noqa: S108 — test-only
PRIVATE_DIR = "/tmp/private"  # noqa: S108 — test-only
T9N_DEFAULT_LANG = "en"
IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM = True
MIGRATION_0023_MECHANISM = 1

STOCK_ALERTS_PRODUCT_URL = {"default-europe": "https://shop.example/{country}/product/{url_key}?variant={sku}"}
STOCK_ALERTS_CANCEL_URL = {"default-europe": "https://shop.example/{country}/stock-alert/cancel?token={token}"}
