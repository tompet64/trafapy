"""
Test suite for TrafaPy - Trafikanalys API Python Wrapper

This test suite covers:
- Core client functionality
- Caching system
- Data retrieval and processing
- API structure exploration
- Error handling

Run with: pytest test_trafapy.py -v
"""

import pytest
import pandas as pd
import json
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Import the modules we're testing
from trafapy.client import TrafikanalysClient, APIResponseError
from trafapy.cache_utils import APICache, cached_api_request


class TestAPICache:
    """Test the caching functionality."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache = APICache(cache_dir=self.temp_dir, expiry_seconds=3600, enabled=True)
    
    def teardown_method(self):
        """Clean up after each test."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_cache_initialization(self):
        """Test cache initialization."""
        assert self.cache.cache_dir == self.temp_dir
        assert self.cache.expiry_seconds == 3600
        assert self.cache.enabled == True
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        url = "https://api.trafa.se/api/structure"
        params = {"lang": "sv", "query": "t10016"}
        
        key1 = self.cache.generate_cache_key(url, params)
        key2 = self.cache.generate_cache_key(url, params)
        
        # Same input should generate same key
        assert key1 == key2
        
        # Different input should generate different key
        params_different = {"lang": "en", "query": "t10016"}
        key3 = self.cache.generate_cache_key(url, params_different)
        assert key1 != key3
    
    def test_cache_save_and_retrieve(self):
        """Test saving and retrieving from cache."""
        cache_key = "test_key"
        test_data = {"test": "data", "number": 123}
        
        # Save to cache
        success = self.cache.save_to_cache(cache_key, test_data)
        assert success == True
        
        # Retrieve from cache
        retrieved_data = self.cache.get_from_cache(cache_key)
        assert retrieved_data == test_data
    
    def test_cache_expiry(self):
        """Test cache expiry functionality."""
        # Create cache with very short expiry
        short_cache = APICache(cache_dir=self.temp_dir, expiry_seconds=1, enabled=True)
        
        cache_key = "test_expiry"
        test_data = {"test": "expiry"}
        
        # Save to cache
        short_cache.save_to_cache(cache_key, test_data)
        
        # Should be valid immediately
        assert short_cache.is_cache_valid(cache_key) == True
        
        # Wait for expiry (in real test, we'd mock time)
        import time
        time.sleep(1.1)
        
        # Should be expired now
        assert short_cache.is_cache_valid(cache_key) == False
    
    def test_cache_disabled(self):
        """Test cache behavior when disabled."""
        disabled_cache = APICache(enabled=False)
        
        cache_key = "test_disabled"
        test_data = {"test": "disabled"}
        
        # Save should return False when disabled
        success = disabled_cache.save_to_cache(cache_key, test_data)
        assert success == False
        
        # Retrieve should return None when disabled
        retrieved_data = disabled_cache.get_from_cache(cache_key)
        assert retrieved_data == None
    
    def test_cache_info(self):
        """Test cache information retrieval."""
        # Get info on empty cache
        info = self.cache.get_cache_info()
        assert info["enabled"] == True
        assert info["file_count"] == 0
        assert info["total_size_bytes"] == 0
        
        # Add some data
        self.cache.save_to_cache("key1", {"data": "test1"})
        self.cache.save_to_cache("key2", {"data": "test2"})
        
        # Check updated info
        info = self.cache.get_cache_info()
        assert info["file_count"] == 2
        assert info["total_size_bytes"] > 0
    
    def test_cache_clear(self):
        """Test cache clearing functionality."""
        # Add some data
        self.cache.save_to_cache("key1", {"data": "test1"})
        self.cache.save_to_cache("key2", {"data": "test2"})
        
        # Clear all
        count = self.cache.clear_cache()
        assert count == 2
        
        # Verify cache is empty
        info = self.cache.get_cache_info()
        assert info["file_count"] == 0


class TestTrafikanalysClient:
    """Test the main client functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            language="sv", 
            debug=False, 
            cache_enabled=True,
            cache_dir=self.temp_dir,
            cache_expiry_seconds=3600
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.language == "sv"
        assert self.client.BASE_URL == "https://api.trafa.se/api"
        assert self.client.cache.enabled == True
    
    @patch('requests.Session.get')
    def test_make_request_success(self, mock_get):
        """Test successful API request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_get.return_value = mock_response
        
        url = "https://api.trafa.se/api/structure"
        params = {"lang": "sv"}
        
        result = self.client._make_request(url, params)
        assert result == {"test": "data"}
        mock_get.assert_called_once_with(url, params=params)
    
    @patch('requests.Session.get')
    def test_make_request_failure(self, mock_get):
        """Test failed API request."""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_get.return_value = mock_response
        
        url = "https://api.trafa.se/api/structure"
        params = {"lang": "sv"}
        
        with pytest.raises(APIResponseError, match="HTTP 404"):
            self.client._make_request(url, params)

    @patch('requests.Session.get')
    def test_make_request_rejects_api_errors_in_http_200(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Rows": [], "Errors": ["Invalid selection"]}
        mock_get.return_value = mock_response

        with pytest.raises(APIResponseError, match="Invalid selection"):
            self.client._make_request("https://api.trafa.se/api/data", {"query": "bad"})

    def test_data_request_rejects_cached_api_error_response(self):
        url = f"{self.client.BASE_URL}/data"
        params = {"query": "t10011|ar:2020", "lang": "sv"}
        key = self.client.cache.generate_cache_key(url, params)
        self.client.cache.save_to_cache(key, {"Rows": [], "Errors": ["Invalid selection"]})

        with pytest.raises(APIResponseError, match="Invalid selection"):
            self.client._get_data(params["query"])
    
    def test_build_query(self):
        """Test query building functionality."""
        product_code = "t10016"
        variables = {
            "ar": ["2020", "2021"],
            "drivmedel": "101",
            "bestand": ""
        }
        
        query = self.client._build_query(product_code, variables)
        expected = "t10016|ar:2020,2021|drivmedel:101|bestand"
        assert query == expected
    
    def test_build_query_empty_variables(self):
        """Test query building with empty variables."""
        product_code = "t10016"
        variables = {}
        
        query = self.client._build_query(product_code, variables)
        assert query == "t10016"
    
    def test_build_query_single_values(self):
        """Test query building with single values."""
        product_code = "t10016"
        variables = {
            "ar": "2020",
            "drivmedel": ["101", "102"]
        }
        
        query = self.client._build_query(product_code, variables)
        expected = "t10016|ar:2020|drivmedel:101,102"
        assert query == expected
    
    @patch('trafapy.client.TrafikanalysClient._make_request')
    def test_list_products(self, mock_request):
        """Test listing products."""
        # Mock API response
        mock_response = {
            "StructureItems": [
                {
                    "Name": "t10016",
                    "Label": "Personbilar",
                    "Description": "Statistics about passenger cars",
                    "Id": "291",
                    "UniqueId": "T10016",
                    "ActiveFrom": "2022-05-10T14:00:00"
                },
                {
                    "Name": "t10013",
                    "Label": "Lastbilar",
                    "Description": "Statistics about trucks",
                    "Id": "292",
                    "UniqueId": "T10013",
                    "ActiveFrom": "2022-05-12T08:00:00"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        products_df = self.client.list_products()
        
        assert isinstance(products_df, pd.DataFrame)
        assert len(products_df) == 2
        assert "t10016" in products_df["code"].values
        assert "t10013" in products_df["code"].values
        assert "Personbilar" in products_df["label"].values
        assert "Lastbilar" in products_df["label"].values
    
    @patch('trafapy.client.TrafikanalysClient._make_request')
    def test_list_products_empty_response(self, mock_request):
        """Test listing products with empty response."""
        mock_request.return_value = {}
        
        products_df = self.client.list_products()
        assert isinstance(products_df, pd.DataFrame)
        assert len(products_df) == 0
    
    @patch('trafapy.client.TrafikanalysClient.list_products')
    def test_search_products(self, mock_list_products):
        """Test product search functionality."""
        # Mock products dataframe
        products_data = pd.DataFrame([
            {
                "code": "t10016",
                "label": "Personbilar",
                "description": "Statistics about passenger cars",
                "id": "291",
                "unique_id": "T10016",
                "active_from": "2022-05-10T14:00:00"
            },
            {
                "code": "t10013",
                "label": "Lastbilar", 
                "description": "Statistics about trucks",
                "id": "292",
                "unique_id": "T10013",
                "active_from": "2022-05-12T08:00:00"
            }
        ])
        mock_list_products.return_value = products_data
        
        # Search for cars
        results = self.client.search_products("personbilar")
        assert len(results) == 1
        assert results.iloc[0]["code"] == "t10016"
        
        # Search for trucks
        results = self.client.search_products("lastbilar")
        assert len(results) == 1
        assert results.iloc[0]["code"] == "t10013"
        
        # Search with no matches
        results = self.client.search_products("nonexistent")
        assert len(results) == 0
    
    def test_process_row(self):
        """Test row processing functionality."""
        # Test with list of cells
        row_data = {
            "Cell": [
                {"Column": "ar", "Value": "2020"},
                {"Column": "antal", "Value": "12345"}
            ]
        }
        
        processed = self.client._process_row(row_data)
        expected = {"ar": "2020", "antal": "12345"}
        assert processed == expected
        
        # Test with single cell
        row_data_single = {
            "Cell": {"Column": "ar", "Value": "2020"}
        }
        
        processed_single = self.client._process_row(row_data_single)
        expected_single = {"ar": "2020"}
        assert processed_single == expected_single
    
    def test_data_to_dataframe(self):
        """Test data to DataFrame conversion."""
        # Mock API data response
        api_data = {
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
        
        df = self.client._data_to_dataframe(api_data)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["ar", "antal"]
        assert df.iloc[0]["ar"] == "2020"
        assert df.iloc[1]["ar"] == "2021"
    
    def test_data_to_dataframe_empty(self):
        """Test data to DataFrame conversion with empty data."""
        empty_data = {"Rows": []}
        df = self.client._data_to_dataframe(empty_data)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        
        # Test with no data at all
        no_data = {}
        df = self.client._data_to_dataframe(no_data)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


class TestClientIntegration:
    """Small live API checks, selected separately with ``-m integration``."""

    PRODUCT = "t10011"  # Buses; also used by the captured metadata regressions.
    YEAR = "2023"       # Fixed historical period, not a moving "latest" value.

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        """Require fresh, bounded HTTP requests and fail on API-reported errors."""
        client = TrafikanalysClient(
            language="sv",
            cache_enabled=False,
            cache_dir=str(tmp_path),
            enable_retry=False,
        )
        original_get = client.session.get

        def checked_get(url, **kwargs):
            # The production client currently supplies no timeout. Bound only
            # these live tests without changing the client's public behavior.
            kwargs.setdefault("timeout", (10, 30))
            response = original_get(url, **kwargs)
            response.raise_for_status()
            payload = response.json()
            assert isinstance(payload, dict), "Expected an API response object"
            assert not payload.get("Errors"), "API errors: {!r}".format(payload.get("Errors"))
            return response

        monkeypatch.setattr(client.session, "get", checked_get)
        try:
            yield client
        finally:
            client.session.close()

    @pytest.mark.integration
    def test_real_api_list_products(self, client):
        """The catalogue must contain the exact product needed by these checks."""
        products = client.list_products()

        assert isinstance(products, pd.DataFrame)
        assert not products.empty, "The live product catalogue is empty"
        assert {"code", "label"}.issubset(products.columns)
        assert products["code"].notna().all()
        assert products["code"].is_unique, "Duplicate product codes in catalogue"
        selected = products.loc[products["code"] == self.PRODUCT]
        assert len(selected) == 1, "Expected product t10011 in the live catalogue"
        assert selected["label"].notna().all()
        assert selected["label"].str.strip().ne("").all()

    @pytest.mark.integration
    def test_real_api_explore_variables(self, client):
        """Require D/M/H metadata and usable direct options for a hierarchy child."""
        variables = client.explore_product_variables(self.PRODUCT)

        assert isinstance(variables, pd.DataFrame)
        assert not variables.empty, "The live product metadata is empty"
        assert {"name", "label", "type", "parent_hierarchy"}.issubset(variables.columns)
        assert variables["name"].is_unique
        rows = variables.set_index("name")
        expected_types = {
            "ar": "Variable", "itrfslut": "Measure",
            "agare": "Hierarchy", "agarkat": "Variable",
        }
        assert set(expected_types).issubset(rows.index)
        for name, expected_type in expected_types.items():
            assert rows.loc[name, "type"] == expected_type
            assert pd.notna(rows.loc[name, "label"])
            assert rows.loc[name, "label"].strip()
        assert rows.loc["agarkat", "parent_hierarchy"] == "agare"

        # Spy on the fallback rather than replacing it: a live direct lookup
        # must work on its own, including recursive search within its response.
        with patch.object(
            client, "_explore_variable_options_hierarchical",
            wraps=client._explore_variable_options_hierarchical,
        ) as fallback:
            options = client.explore_variable_options(self.PRODUCT, "agarkat")
            fallback.assert_not_called()
        assert not options.empty, "Direct hierarchy-child lookup returned no options"
        assert {"name", "label", "option_type"}.issubset(options.columns)
        values = options.loc[options["option_type"] == "Value"]
        assert {"10", "20", "t1"}.issubset(set(values["name"]))
        assert values["label"].notna().all()
        assert values["label"].str.strip().ne("").all()

    @pytest.mark.integration
    def test_real_api_get_data_small(self, client):
        """A one-year national count must be nonempty, numeric and correctly selected."""
        data = client.get_data_as_dataframe(
            self.PRODUCT, {"ar": [self.YEAR], "itrfslut": ""}
        )

        assert isinstance(data, pd.DataFrame)
        assert not data.empty, "The live statistics query returned no rows"
        assert {"ar", "itrfslut"}.issubset(data.columns)
        assert len(data) == 1, "Expected one national annual count"
        assert data["ar"].astype(str).tolist() == [self.YEAR]
        counts = pd.to_numeric(data["itrfslut"], errors="raise")
        assert counts.notna().all(), "Missing count in live statistics response"
        assert (counts > 0).all(), "Expected a positive bus count"
        assert (counts % 1 == 0).all(), "Expected an integer count"


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('requests.Session.get')
    def test_network_error_handling(self, mock_get):
        """Test handling of network errors."""
        import requests
        mock_get.side_effect = requests.ConnectionError("Network error")
        
        # Should not raise exception, but return empty result
        with pytest.raises(requests.ConnectionError):
            self.client._make_request("https://api.trafa.se/api/structure", {})
    
    def test_invalid_json_response(self):
        """Test handling of invalid JSON responses."""
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_get.return_value = mock_response
            
            with pytest.raises(json.JSONDecodeError):
                self.client._make_request("https://api.trafa.se/api/structure", {})
    
    def test_malformed_api_response(self):
        """Test handling of malformed API responses."""
        malformed_data = {
            "unexpected_structure": "data"
        }
        
        df = self.client._data_to_dataframe(malformed_data)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


class TestUtilityFunctions:
    """Test utility and convenience functions."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('trafapy.client.TrafikanalysClient.explore_variable_options')
    def test_get_all_available_values(self, mock_explore):
        """Test getting all available values for a variable."""
        # Mock the explore_variable_options method
        mock_options = pd.DataFrame([
            {"name": "2020", "label": "2020", "description": "", "option_type": "Value"},
            {"name": "2021", "label": "2021", "description": "", "option_type": "Value"},
            {"name": "2022", "label": "2022", "description": "", "option_type": "Value"},
            {"name": "t1", "label": "Totalt", "description": "", "option_type": "Value"}
        ])
        mock_explore.return_value = mock_options
        
        values = self.client.get_all_available_values("t10016", "ar")
        
        # Should exclude 't1' by default and sort years
        expected = ["2020", "2021", "2022"]
        assert values == expected
    
    @patch('trafapy.client.TrafikanalysClient.get_all_available_values')
    def test_build_query_automated(self, mock_get_values):
        """Test automated query building."""
        # Mock the get_all_available_values method
        mock_get_values.side_effect = lambda product, var: {
            "ar": ["2020", "2021", "2022"],
            "drivmedel": ["101", "102", "103"]
        }.get(var, [])
        
        query_dict = self.client.build_query(
            "t10016",
            ar="all",
            drivmedel="all",
            reglan=["01"],
            bestand=""
        )
        
        expected = {
            "ar": ["2020", "2021", "2022"],
            "drivmedel": ["101", "102", "103"],
            "reglan": ["01"],
            "bestand": ""
        }
        
        assert query_dict == expected
    
    def test_preview_query(self):
        """Test query preview functionality."""
        query_dict = {
            "ar": ["2020", "2021"],
            "drivmedel": "101",
            "bestand": ""
        }
        
        # Capture printed output
        import io
        import sys
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        query_string = self.client.preview_query("t10016", query_dict)
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        
        expected_query = "t10016|ar:2020,2021|drivmedel:101|bestand"
        assert query_string == expected_query
        
        # Check that URL was printed
        output = captured_output.getvalue()
        assert "https://api.trafa.se/api/data?query=" in output


# Test configuration and markers
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (may hit real API)"
    )


# Example of how to run different test categories:
# 
# Run all tests:
# pytest test_trafapy.py -v
#
# Run only unit tests (exclude integration):
# pytest test_trafapy.py -v -m "not integration"
#
# Run only integration tests:
# pytest test_trafapy.py -v -m integration
#
# Run with coverage:
# pytest test_trafapy.py --cov=trafapy --cov-report=html


if __name__ == "__main__":
    # Run the tests if this file is executed directly
    pytest.main([__file__, "-v"])
