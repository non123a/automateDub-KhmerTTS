from __future__ import annotations

from automatedub_studio.app import APPLICATION_NAME, ORGANIZATION_NAME, create_application


def test_create_application_sets_names(qapp):
    app = create_application([])

    assert app.organizationName() == ORGANIZATION_NAME
    assert app.applicationName() == APPLICATION_NAME


def test_create_application_reuses_existing_instance(qapp):
    app = create_application([])

    assert app is qapp
