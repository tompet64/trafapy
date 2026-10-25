"""
Test suite for TrafaPy convenience functions and advanced features.

This test file focuses on:
- Advanced query building
- Convenience functions
- Edge cases and error scenarios
- Performance testing
- Real-world usage patterns
"""

import pytest
import pandas as pd
import time
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

from trafapy.client import TrafikanalysClient
from trafapy.cache_utils import APICache


class TestAdvancedQueryBuilding:
    """Test advanced query building features."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir,
            debug=False
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_build_query_with_all_values(self):
        """Test building query with 'all' values."""
        with patch.object(self.client, 'get_all_available_values') as mock_get_values:
            mock_get_values.side_effect = lambda product, var: {
                "ar": ["2020", "2021", "2022"],
                "drivmedel": ["101", "102", "103", "104"]
            }.get(var, [])
            
            query_dict = self.client.build_query(
                "t10016",
                ar="all",
                drivmedel="all",
                bestand=""
            )
            
            assert query_dict["ar"] == ["2020", "2021", "2022"]
            assert query_dict["drivmedel"] == ["101", "102", "103", "104"]
            assert query_dict["bestand"] == ""
    
    def test_build_query_with_all_years_alias(self):
        """Test building query with 'all_years' alias."""
        with patch.object(self.client, 'get_all_available_values') as mock_get_values:
            mock_get_values.return_value = ["2020", "2021", "2022"]
            
            query_dict = self.client.build_query(
                "t10016",
                ar="all"
            )
            
            assert query_dict["ar"] == ["2020", "2021", "2022"]
            mock_get_values.assert_called_with("t10016", "ar")
    
    def test_build_query_mixed_parameters(self):
        """Test building query with mixed parameter types."""
        with patch.object(self.client, 'get_all_available_values') as mock_get_values:
            mock_get_values.side_effect = lambda product, var: {
                "ar": ["2020", "2021", "2022"],
                "reglan": ["01", "02", "03"]
            }.get(var, [])
            
            query_dict = self.client.build_query(
                "t10016",
                ar="all",                    # Get all years
                reglan=["01"],              # Specific region
                drivmedel="101",            # Single value
                bestand=""                  # No filter
            )
            
            assert query_dict["ar"] == ["2020", "2021", "2022"]
            assert query_dict["reglan"] == ["01"]
            assert query_dict["drivmedel"] == "101"
            assert query_dict["bestand"] == ""
    
    def test_get_all_available_values_year_sorting(self):
        """Test that years are properly sorted."""
        mock_options = pd.DataFrame([
            {"name": "2022", "label": "2022", "option_type": "Value"},
            {"name": "2020", "label": "2020", "option_type": "Value"},
            {"name": "2021", "label": "2021", "option_type": "Value"},
            {"name": "t1", "label": "Totalt", "option_type": "Value"},
            {"name": "senaste", "label": "Senaste", "option_type": "Filter"}
        ])
        
        with patch.object(self.client, 'explore_variable_options') as mock_explore:
            mock_explore.return_value = mock_options
            
            values = self.client.get_all_available_values("t10016", "ar")
            
            # Should be sorted and exclude totals and filters
            assert values == ["2020", "2021", "2022"]
    
    def test_get_all_available_values_exclude_totals(self):
        """Test excluding total values."""
        mock_options = pd.DataFrame([
            {"name": "101", "label": "Bensin", "option_type": "Value"},
            {"name": "102", "label": "Diesel", "option_type": "Value"},
            {"name": "t1", "label": "Totalt", "option_type": "Value"},
            {"name": "totalt", "label": "Totalt", "option_type": "Value"}
        ])
        
        with patch.object(self.client, 'explore_variable_options') as mock_explore:
            mock_explore.return_value = mock_options
            
            # With exclude_totals=True (default)
            values = self.client.get_all_available_values("t10016", "drivmedel")
            assert values == ["101", "102"]
            
            # With exclude_totals=False
            values_with_totals = self.client.get_all_available_values(
                "t10016", "drivmedel", exclude_totals=False
            )
            assert "t1" in values_with_totals
            assert "totalt" in values_with_totals
    
    def test_get_all_available_values_empty_options(self):
        """Test handling of empty options."""
        with patch.object(self.client, 'explore_variable_options') as mock_explore:
            mock_explore.return_value = pd.DataFrame()
            
            values = self.client.get_all_available_values("t10016", "nonexistent")
            assert values == []


class TestVariableExploration:
    """Test variable exploration functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir,
            debug=False
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('trafapy.client.TrafikanalysClient._get_structure')
    def test_explore_product_variables_hierarchical(
        self, mock_get_structure, captured_bus_structure
    ):
        """Captured product has top-level variables linked by ParentName."""
        mock_get_structure.return_value = captured_bus_structure

        variables_df = self.client.explore_product_variables("t10011")

        assert len(variables_df) == 14
        variable_types = variables_df.set_index('name')['type'].to_dict()
        assert variable_types['ar'] == 'Variable'
        assert variable_types['agare'] == 'Hierarchy'
        assert variable_types['agarkat'] == 'Variable'
        assert variable_types['itrfslut'] == 'Measure'
        hierarchy_info = variables_df.set_index('name')['parent_hierarchy'].to_dict()
        assert pd.isna(hierarchy_info['ar'])
        assert pd.isna(hierarchy_info['agare'])
        assert hierarchy_info['agarkat'] == 'agare'
        assert hierarchy_info['tillst'] == 'agare'
        mock_get_structure.assert_called_once_with(query="t10011")

    @patch('trafapy.client.TrafikanalysClient._make_request')
    def test_explore_variable_options_direct_access(self, mock_request):
        """Test exploring variable options with direct access."""
        mock_response = {
            "StructureItems": [
                {
                    "Name": "ar",
                    "Label": "År",
                    "Type": "D",
                    "StructureItems": [
                        {"Name": "2020", "Label": "2020", "Type": "DV"},
                        {"Name": "2021", "Label": "2021", "Type": "DV"},
                        {"Name": "senaste", "Label": "Senaste", "Type": "F"}
                    ]
                }
            ]
        }
        mock_request.return_value = mock_response
        
        options_df = self.client.explore_variable_options("t10016", "ar")
        
        assert len(options_df) == 3
        assert "2020" in options_df["name"].values
        assert "2021" in options_df["name"].values
        assert "senaste" in options_df["name"].values
        
        # Check option types
        option_types = options_df.set_index('name')['option_type'].to_dict()
        assert option_types['2020'] == 'Value'
        assert option_types['2021'] == 'Value'
        assert option_types['senaste'] == 'Filter'
    
    @patch('trafapy.client.TrafikanalysClient._make_request')
    def test_explore_variable_options_fallback_to_hierarchical(self, mock_request):
        """Defensive dispatch test; does not establish live fallback reachability."""
        mock_request.return_value = {"StructureItems": []}

        with patch.object(self.client, '_explore_variable_options_hierarchical') as mock_hierarchical:
            mock_hierarchical.return_value = pd.DataFrame([
                {"name": "10", "label": "Fysisk person", "option_type": "Value"},
                {"name": "20", "label": "Juridisk person", "option_type": "Value"}
            ])
            
            options_df = self.client.explore_variable_options("t10016", "agarkat")
            
            assert len(options_df) == 2
            assert "10" in options_df["name"].values
            assert "20" in options_df["name"].values
            mock_hierarchical.assert_called_once_with("t10016", "agarkat")
            mock_request.assert_called_once()


class TestDataProcessing:
    """Test data processing and conversion."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir,
            debug=False
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_process_row_complex_structure(self):
        """Test processing complex row structures."""
        # Test with mixed cell types
        complex_row = {
            "Cell": [
                {"Column": "ar", "Value": "2020", "FormattedValue": "2020"},
                {"Column": "antal", "Value": "12345", "IsMeasure": True},
                {"Column": "region", "Value": "Stockholm", "Description": "Stockholm region"}
            ]
        }
        
        processed = self.client._process_row(complex_row)
        expected = {
            "ar": "2020",
            "antal": "12345",
            "region": "Stockholm"
        }
        assert processed == expected
    
    def test_process_row_empty_cells(self):
        """Test processing rows with empty or missing cells."""
        # Test with missing Column value
        row_with_missing = {
            "Cell": [
                {"Column": "ar", "Value": "2020"},
                {"Value": "12345"},  # Missing Column
                {"Column": "", "Value": "test"}  # Empty Column
            ]
        }
        
        processed = self.client._process_row(row_with_missing)
        assert processed == {"ar": "2020"}
    
    def test_data_to_dataframe_mixed_row_types(self):
        """Test converting data with mixed row types to DataFrame."""
        mixed_data = {
            "Rows": [
                {
                    "Cell": [
                        {"Column": "ar", "Value": "2020"},
                        {"Column": "antal", "Value": "12345"}
                    ]
                },
                {
                    "Cell": {"Column": "ar", "Value": "2021"}  # Single cell
                },
                {
                    "Cell": [
                        {"Column": "ar", "Value": "2022"},
                        {"Column": "antal", "Value": "13456"},
                        {"Column": "region", "Value": "Göteborg"}
                    ]
                }
            ]
        }
        
        df = self.client._data_to_dataframe(mixed_data)
        
        assert len(df) == 3
        assert "ar" in df.columns
        assert "antal" in df.columns
        assert "region" in df.columns
        
        # Check that missing values are handled properly
        assert df.iloc[1]["antal"] != df.iloc[1]["antal"]  # NaN check
        assert df.iloc[0]["region"] != df.iloc[0]["region"]  # NaN check


class TestCachePerformance:
    """Test cache performance and optimization."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache = APICache(
            cache_dir=self.temp_dir,
            expiry_seconds=3600,
            enabled=True
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cache_performance_large_data(self):
        """Test cache performance with large datasets."""
        # Create large test data
        large_data = {
            "test_data": list(range(10000)),
            "metadata": {"size": "large", "description": "Performance test data"}
        }
        
        cache_key = "performance_test"
        
        # Time saving to cache
        start_time = time.time()
        success = self.cache.save_to_cache(cache_key, large_data)
        save_time = time.time() - start_time
        
        assert success == True
        assert save_time < 1.0  # Should save within 1 second
        
        # Time retrieval from cache
        start_time = time.time()
        retrieved_data = self.cache.get_from_cache(cache_key)
        retrieve_time = time.time() - start_time
        
        assert retrieved_data == large_data
        assert retrieve_time < 0.1  # Should retrieve within 0.1 seconds
    
    def test_cache_concurrent_access(self):
        """Test cache behavior with concurrent access patterns."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def cache_worker(worker_id):
            """Worker function to test concurrent cache access."""
            try:
                cache_key = f"worker_{worker_id}"
                test_data = {"worker_id": worker_id, "data": list(range(100))}
                
                # Save data
                success = self.cache.save_to_cache(cache_key, test_data)
                assert success == True
                
                # Retrieve data
                retrieved = self.cache.get_from_cache(cache_key)
                assert retrieved == test_data
                
                results.put(("success", worker_id))
            except Exception as e:
                results.put(("error", worker_id, str(e)))
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)
        
        # Check results
        success_count = 0
        while not results.empty():
            result = results.get()
            if result[0] == "success":
                success_count += 1
            else:
                pytest.fail(f"Worker {result[1]} failed: {result[2]}")
        
        assert success_count == 5


class TestErrorScenarios:
    """Test various error scenarios and edge cases."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir,
            debug=False
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_malformed_query_parameters(self):
        """Test handling of malformed query parameters."""
        # Test with None values
        query_dict = self.client.build_query(
            "t10016",
            ar=None,
            drivmedel="",
            bestand=None
        )
        
        # Should handle None values gracefully
        assert "ar" not in query_dict or query_dict["ar"] is None
        assert query_dict["drivmedel"] == ""
    
    def test_invalid_product_code(self):
        """Test handling of invalid product codes."""
        with patch.object(self.client, '_get_structure') as mock_get_structure:
            mock_get_structure.return_value = {"StructureItems": []}
            
            variables_df = self.client.explore_product_variables("invalid_product")
            assert len(variables_df) == 0
    
    def test_network_timeout_simulation(self):
        """Test handling of network timeouts."""
        import requests
        
        with patch('requests.Session.get') as mock_get:
            mock_get.side_effect = requests.Timeout("Connection timeout")
            
            with pytest.raises(requests.Timeout):
                self.client._make_request("https://api.trafa.se/api/structure", {})
    
    def test_api_rate_limiting_simulation(self):
        """Test handling of API rate limiting with retry logic."""
        import requests
        
        with patch('requests.Session.get') as mock_get:
            with patch('time.sleep') as mock_sleep:  # Speed up the test
                # All requests return 429 (rate limited)
                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.text = "Rate limit exceeded"
                mock_get.return_value = mock_response
                
                # Should exhaust retries and raise an exception
                with pytest.raises(requests.exceptions.RequestException):
                    self.client._make_request("https://api.trafa.se/api/structure", {})
                
                # Verify that retries were attempted
                assert mock_get.call_count > 1  # Should have retried
                assert mock_sleep.call_count > 0  # Should have waited between retries
    
    def test_corrupted_cache_file(self):
        """Test handling of corrupted cache files."""
        cache_key = "corrupted_test"
        cache_path = self.client.cache.get_cache_path(cache_key)
        
        # Create cache directory
        self.client.cache._ensure_cache_dir_exists()
        
        # Write corrupted JSON to cache file
        with open(cache_path, 'w') as f:
            f.write("{'invalid': json}")
        
        # Should handle corrupted cache gracefully
        retrieved = self.client.cache.get_from_cache(cache_key)
        assert retrieved is None
    
    def test_memory_pressure_large_cache(self):
        """Test cache behavior under memory pressure."""
        # Fill cache with many large items
        large_items = {}
        for i in range(50):
            key = f"large_item_{i}"
            data = {"id": i, "large_data": list(range(1000))}
            
            success = self.client.cache.save_to_cache(key, data)
            assert success == True
            large_items[key] = data
        
        # Verify all items can still be retrieved
        for key, expected_data in large_items.items():
            retrieved = self.client.cache.get_from_cache(key)
            assert retrieved == expected_data


class TestRealWorldUsagePatterns:
    """Test realistic usage patterns and workflows."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir,
            debug=False
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('trafapy.client.TrafikanalysClient.list_products')
    @patch('trafapy.client.TrafikanalysClient.get_data_as_dataframe')
    def test_typical_research_workflow(self, mock_get_data, mock_list_products):
        """Test a typical research workflow."""
        # Mock products list
        mock_list_products.return_value = pd.DataFrame([
            {"code": "t10016", "label": "Personbilar", "description": "Passenger cars"},
            {"code": "t10013", "label": "Lastbilar", "description": "Trucks"}
        ])
        
        # Mock data response
        mock_get_data.return_value = pd.DataFrame([
            {"ar": "2020", "antal": "100000", "drivmedel": "Bensin"},
            {"ar": "2021", "antal": "95000", "drivmedel": "Bensin"},
            {"ar": "2022", "antal": "90000", "drivmedel": "Bensin"}
        ])
        
        # Step 1: Find relevant products
        products = self.client.list_products()
        car_products = self.client.search_products("personbilar")
        assert len(car_products) == 1
        
        # Step 2: Get data for analysis
        product_code = car_products.iloc[0]["code"]
        data = self.client.get_data_as_dataframe(
            product_code,
            {"ar": ["2020", "2021", "2022"], "drivmedel": "101"}
        )
        
        # Step 3: Verify data structure
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 3
        assert "ar" in data.columns
        assert "antal" in data.columns
    
    def test_iterative_query_building(self):
        """Test iterative query building process."""
        with patch.object(self.client, 'explore_product_variables') as mock_explore_vars:
            with patch.object(self.client, 'explore_variable_options') as mock_explore_options:
                with patch.object(self.client, 'get_data_as_dataframe') as mock_get_data:
                    
                    # Mock variables exploration
                    mock_explore_vars.return_value = pd.DataFrame([
                        {"name": "ar", "label": "År", "type": "Variable", "has_filter_options": True},
                        {"name": "drivmedel", "label": "Drivmedel", "type": "Variable", "has_filter_options": True},
                        {"name": "bestand", "label": "Bestånd", "type": "Measure", "has_filter_options": False}
                    ])
                    
                    # Mock options exploration
                    def mock_options_func(product, variable):
                        if variable == "ar":
                            return pd.DataFrame([
                                {"name": "2020", "label": "2020", "option_type": "Value"},
                                {"name": "2021", "label": "2021", "option_type": "Value"}
                            ])
                        elif variable == "drivmedel":
                            return pd.DataFrame([
                                {"name": "101", "label": "Bensin", "option_type": "Value"},
                                {"name": "102", "label": "Diesel", "option_type": "Value"}
                            ])
                        return pd.DataFrame()
                    
                    mock_explore_options.side_effect = mock_options_func
                    
                    # Mock data retrieval
                    mock_get_data.return_value = pd.DataFrame([
                        {"ar": "2020", "drivmedel": "Bensin", "bestand": "50000"}
                    ])
                    
                    # Simulate iterative workflow
                    product_code = "t10016"
                    
                    # Step 1: Explore available variables
                    variables = self.client.explore_product_variables(product_code)
                    assert len(variables) == 3
                    
                    # Step 2: Explore options for each variable
                    year_options = self.client.explore_variable_options(product_code, "ar")
                    fuel_options = self.client.explore_variable_options(product_code, "drivmedel")
                    
                    assert len(year_options) == 2
                    assert len(fuel_options) == 2
                    
                    # Step 3: Build and execute query
                    query_dict = {
                        "ar": ["2020"],
                        "drivmedel": "101",
                        "bestand": ""
                    }
                    
                    data = self.client.get_data_as_dataframe(product_code, query_dict)
                    assert len(data) == 1
    
    def test_data_export_workflow(self):
        """Test workflow for data export and analysis."""
        # Mock data for export testing
        test_data = pd.DataFrame([
            {"year": "2020", "fuel_type": "Gasoline", "count": "100000", "region": "Stockholm"},
            {"year": "2021", "fuel_type": "Gasoline", "count": "95000", "region": "Stockholm"},
            {"year": "2020", "fuel_type": "Diesel", "count": "80000", "region": "Stockholm"},
            {"year": "2021", "fuel_type": "Diesel", "count": "75000", "region": "Stockholm"}
        ])
        
        with patch.object(self.client, 'get_data_as_dataframe') as mock_get_data:
            mock_get_data.return_value = test_data
            
            # Get data
            data = self.client.get_data_as_dataframe("t10016", {"ar": ["2020", "2021"]})
            
            # Test data manipulation and export
            assert len(data) == 4
            # pandas 3 infers a string dtype; older pandas uses object.
            assert pd.api.types.is_string_dtype(data["count"])
            
            # Convert to numeric for analysis
            data_numeric = data.copy()
            data_numeric["count"] = pd.to_numeric(data_numeric["count"])
            
            # Basic analysis
            total_by_year = data_numeric.groupby("year")["count"].sum()
            assert total_by_year["2020"] == 180000
            assert total_by_year["2021"] == 170000
    
    def test_cache_warming_strategy(self):
        """Test strategy for warming up the cache."""
        common_queries = [
            {"product": "t10016", "vars": {"ar": ["2022"], "bestand": ""}},
            {"product": "t10016", "vars": {"ar": ["2021"], "bestand": ""}},
            {"product": "t10013", "vars": {"ar": ["2022"], "bestand": ""}}
        ]
        
        # Mock at the HTTP request level so caching still works
        with patch.object(self.client, '_make_request') as mock_request:
            mock_request.return_value = {"Rows": []}
            
            # Warm up cache with common queries
            for query_spec in common_queries:
                self.client.get_data_as_dataframe(
                    query_spec["product"],
                    query_spec["vars"]
                )
            
            # Verify cache has been populated
            cache_info = self.client.get_cache_info()
            assert cache_info["file_count"] >= len(common_queries)
    
    def test_error_recovery_workflow(self):
        """Test error recovery in typical workflows."""
        with patch('requests.Session.get') as mock_get:
            # Simulate intermittent network issues
            call_count = 0
            
            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                
                if call_count <= 2:
                    # First two calls fail
                    import requests
                    raise requests.ConnectionError("Network error")
                else:
                    # Subsequent calls succeed
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"StructureItems": []}
                    return mock_response
            
            mock_get.side_effect = side_effect
            
            # First attempts should fail
            with pytest.raises(Exception):
                self.client.list_products()
            
            with pytest.raises(Exception):
                self.client.list_products()
            
            # Third attempt should succeed
            products = self.client.list_products()
            assert isinstance(products, pd.DataFrame)


class TestPerformanceOptimization:
    """Test performance optimization features."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = TrafikanalysClient(
            cache_enabled=True,
            cache_dir=self.temp_dir,
            cache_expiry_seconds=3600
        )
    
    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_query_optimization(self):
        """Test query optimization for performance."""
        # Test that identical queries use cache
        with patch.object(self.client, '_make_request') as mock_request:
            mock_request.return_value = {"StructureItems": []}
            
            # First call
            self.client.list_products()
            
            # Second identical call should use cache
            self.client.list_products()
            
            # Should only make one actual request
            assert mock_request.call_count == 1
    
    def test_batch_query_efficiency(self):
        """Test efficiency of batch queries."""
        queries = [
            {"ar": ["2020"], "bestand": ""},
            {"ar": ["2021"], "bestand": ""},
            {"ar": ["2022"], "bestand": ""}
        ]
        
        with patch.object(self.client, '_get_data') as mock_get_data:
            mock_get_data.return_value = {"Rows": []}
            
            start_time = time.time()
            
            # Execute batch queries
            results = []
            for query in queries:
                result = self.client.get_data_as_dataframe("t10016", query)
                results.append(result)
            
            elapsed_time = time.time() - start_time
            
            # Should complete relatively quickly
            assert elapsed_time < 1.0  # Less than 1 second for mocked requests
            assert len(results) == 3
    
    def test_memory_efficient_large_dataset(self):
        """Test memory efficiency with large datasets."""
        # Simulate large dataset response
        large_response = {
            "Rows": [
                {"Cell": [{"Column": "ar", "Value": str(year)}, {"Column": "count", "Value": str(i)}]}
                for year in range(2000, 2024)
                for i in range(1000)  # 24,000 rows
            ]
        }
        
        with patch.object(self.client, '_get_data') as mock_get_data:
            mock_get_data.return_value = large_response
            
            # Should handle large dataset without memory issues
            start_time = time.time()
            df = self.client.get_data_as_dataframe("t10016", {"ar": "all", "bestand": ""})
            process_time = time.time() - start_time
            
            assert len(df) == 24000
            assert process_time < 5.0  # Should process within reasonable time


if __name__ == "__main__":
    # Run specific test classes or all tests
    pytest.main([__file__, "-v"])