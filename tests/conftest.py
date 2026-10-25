# conftest.py - Pytest configuration and shared fixtures
import pytest
import tempfile
import shutil
import os
from unittest.mock import Mock
from trafapy.client import TrafikanalysClient


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def client_with_cache(temp_cache_dir):
    """Create a client with temporary cache directory."""
    return TrafikanalysClient(
        language="sv",
        debug=False,
        cache_enabled=True,
        cache_dir=temp_cache_dir,
        cache_expiry_seconds=3600
    )


@pytest.fixture
def client_no_cache():
    """Create a client with caching disabled."""
    return TrafikanalysClient(
        language="sv",
        debug=False,
        cache_enabled=False
    )


@pytest.fixture
def mock_api_response():
    """Mock API response for testing."""
    return {
        "StructureItems": [
            {
                "Name": "t10016",
                "Label": "Personbilar",
                "Description": "Statistics about passenger cars",
                "Id": "291",
                "UniqueId": "T10016",
                "ActiveFrom": "2022-05-10T14:00:00",
                "Type": "P"
            }
        ]
    }


@pytest.fixture
def mock_data_response():
    """Mock data response for testing."""
    return {
        "Header": {
            "Column": [
                {"Name": "ar", "Value": "År", "Type": "D"},
                {"Name": "antal", "Value": "Antal", "Type": "M"}
            ]
        },
        "Rows": [
            {
                "Cell": [
                    {"Column": "ar", "Value": "2020"},
                    {"Column": "antal", "Value": "12345"}
                ]
            },
            {
                "Cell": [
                    {"Column": "ar", "Value": "2021"},
                    {"Column": "antal", "Value": "13456"}
                ]
            }
        ]
    }


# Pytest markers
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (may hit real API)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


@pytest.fixture
def captured_bus_structure():
    """Fresh copy of the full t10011 structure captured on 2026-10-25."""
    import json
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "structure" / "t10011.json"
    return json.loads(path.read_text(encoding="utf-8"))
