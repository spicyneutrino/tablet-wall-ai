"""Shared pytest fixtures for the tablet-wall-ai API tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def isolated_registry() -> Iterator[None]:
    """Keep the in-memory device registry from leaking between tests.

    ``main.devices`` is module-level mutable state, so without this every test
    would see the devices registered by the tests that ran before it.
    """
    main.devices.clear()
    yield
    main.devices.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An HTTP client bound to the app, without starting a network server."""
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def device_payload() -> dict[str, object]:
    """A representative valid registration body."""
    return {
        "device_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
        "width": 1024,
        "height": 768,
        "device_type": "ipad",
    }
