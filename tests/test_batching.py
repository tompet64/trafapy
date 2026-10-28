"""
Test batching functionality for the TrafikanalysClient.

This module contains tests specifically for the batching mechanism that splits
large queries into smaller chunks to avoid URL length limits and improve performance.
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from trafapy import TrafikanalysClient, BatchRequestError


class TestBatchingMechanism:
    """Test the batching mechanism for large queries."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TrafikanalysClient(
            cache_enabled=False,
            rate_limit_enabled=False,
            max_batch_size=5,  # Small batch size for testing
            debug=False
        )
    
    def test_needs_batching_detection(self):
        """Test detection of when batching is needed."""
        # Small query - no batching needed
        small_variables = {
            'ar': ['2020', '2021'],
            'reglan': ['01', '03'],
            'nyregunder': ''
        }
        assert not self.client._needs_batching(small_variables)
        
        # Large query - batching needed
        large_variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024', '2025'],  # 6 values > max_batch_size of 5
            'reglan': ['01'],
            'nyregunder': ''
        }
        assert self.client._needs_batching(large_variables)
        
        # Multiple large variables
        multiple_large = {
            'ar': ['2020', '2021', '2022', '2023', '2024', '2025'],  # 6 values
            'reglan': ['01', '02', '03', '04', '05', '06', '07'],    # 7 values
            'nyregunder': ''
        }
        assert self.client._needs_batching(multiple_large)
    
    def test_create_batches_single_variable(self):
        """Test batch creation for a single large variable."""
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024', '2025', '2026', '2027'],  # 8 values
            'reglan': ['01'],
            'nyregunder': ''
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        # Should create 2 batches (5 + 3 values)
        assert len(batches) == 2
        
        # First batch should have 5 years
        assert len(batches[0]['ar']) == 5
        assert batches[0]['ar'] == ['2020', '2021', '2022', '2023', '2024']
        assert batches[0]['reglan'] == ['01']
        assert batches[0]['nyregunder'] == ''
        
        # Second batch should have 3 years
        assert len(batches[1]['ar']) == 3
        assert batches[1]['ar'] == ['2025', '2026', '2027']
        assert batches[1]['reglan'] == ['01']
        assert batches[1]['nyregunder'] == ''
    
    def test_create_batches_multiple_variables(self):
        """Test batch creation when multiple variables are large."""
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024', '2025'],  # 6 values
            'reglan': ['01', '02', '03', '04', '05', '06', '07', '08'],  # 8 values (larger)
            'nyregunder': ''
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        # Should batch by the largest variable (reglan with 8 values)
        # This should create 2 batches (5 + 3 values for reglan)
        assert len(batches) == 2
        
        # Both batches should include all years (since reglan is being batched)
        assert batches[0]['ar'] == ['2020', '2021', '2022', '2023', '2024', '2025']
        assert batches[1]['ar'] == ['2020', '2021', '2022', '2023', '2024', '2025']
        
        # First batch should have 5 regions
        assert len(batches[0]['reglan']) == 5
        assert batches[0]['reglan'] == ['01', '02', '03', '04', '05']
        
        # Second batch should have 3 regions
        assert len(batches[1]['reglan']) == 3
        assert batches[1]['reglan'] == ['06', '07', '08']
    
    def test_create_batches_no_batching_needed(self):
        """Test batch creation when no batching is needed."""
        variables = {
            'ar': ['2020', '2021'],
            'reglan': ['01'],
            'nyregunder': ''
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        # Should return single batch with original variables
        assert len(batches) == 1
        assert batches[0] == variables
    
    def test_batch_size_configuration(self):
        """Test that batch size can be configured."""
        # Change batch size
        self.client.configure_batching(max_batch_size=3)
        
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024'],  # 5 values
            'nyregunder': ''
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        # Should create 2 batches (3 + 2 values)
        assert len(batches) == 2
        assert len(batches[0]['ar']) == 3
        assert len(batches[1]['ar']) == 2
    
    def test_get_batching_info(self):
        """Test getting current batching configuration."""
        info = self.client.get_batching_info()
        
        assert 'max_batch_size' in info
        assert info['max_batch_size'] == 5  # Set in setup_method
        
        # Change configuration and test again
        self.client.configure_batching(max_batch_size=10)
        info = self.client.get_batching_info()
        assert info['max_batch_size'] == 10


class TestBatchingRetrieval:
    """Test batching integration with data retrieval."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TrafikanalysClient(
            cache_enabled=False,
            rate_limit_enabled=False,
            max_batch_size=3,  # Small batch size for testing
            debug=False
        )
    
    @patch.object(TrafikanalysClient, '_get_data')
    def test_get_data_with_batching(self, mock_get_data):
        """Test data retrieval with batching enabled."""
        # Mock API responses for each batch
        mock_response_1 = {
            'Rows': [
                {'Cell': [
                    {'Column': 'ar', 'Value': '2020'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '100'}
                ]},
                {'Cell': [
                    {'Column': 'ar', 'Value': '2021'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '110'}
                ]}
            ]
        }
        
        mock_response_2 = {
            'Rows': [
                {'Cell': [
                    {'Column': 'ar', 'Value': '2022'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '120'}
                ]},
                {'Cell': [
                    {'Column': 'ar', 'Value': '2023'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '130'}
                ]}
            ]
        }
        
        # Set up mock to return different responses for different calls
        mock_get_data.side_effect = [mock_response_1, mock_response_2]
        
        # Variables that require batching (5 years > batch_size of 3)
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024'],
            'reglan': ['01'],
            'nyregunder': ''
        }
        
        # Get data with batching
        df = self.client.get_data_as_dataframe(
            'test_product', 
            variables, 
            use_batching=True,
            show_progress=False
        )
        
        # Should have called _get_data twice (2 batches)
        assert mock_get_data.call_count == 2
        
        # Check the DataFrame has combined data from both batches
        assert len(df) == 4  # 2 rows from first batch + 2 rows from second batch
        assert list(df['ar'].unique()) == ['2020', '2021', '2022', '2023']
        assert all(df['reglan'] == '01')
    
    @patch.object(TrafikanalysClient, '_get_data')
    def test_get_data_without_batching(self, mock_get_data):
        """Test data retrieval with batching disabled."""
        # Mock API response
        mock_response = {
            'Rows': [
                {'Cell': [
                    {'Column': 'ar', 'Value': '2020'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '100'}
                ]}
            ]
        }
        
        mock_get_data.return_value = mock_response
        
        # Variables that would require batching
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024'],
            'reglan': ['01'],
            'nyregunder': ''
        }
        
        # Get data without batching
        df = self.client.get_data_as_dataframe(
            'test_product', 
            variables, 
            use_batching=False,
            show_progress=False
        )
        
        # Should have called _get_data only once
        assert mock_get_data.call_count == 1
        
        # Check the DataFrame
        assert len(df) == 1
    
    @patch.object(TrafikanalysClient, '_get_data')
    def test_batch_error_rejects_partial_result_by_default(self, mock_get_data):
        """A failed batch must not silently produce a complete-looking frame."""
        # Mock: first batch succeeds, second batch fails
        mock_response_1 = {
            'Rows': [
                {'Cell': [
                    {'Column': 'ar', 'Value': '2020'},
                    {'Column': 'nyregunder', 'Value': '100'}
                ]}
            ]
        }
        
        def side_effect(*args, **kwargs):
            if mock_get_data.call_count == 1:
                return mock_response_1
            else:
                raise Exception("API Error")
        
        mock_get_data.side_effect = side_effect
        
        # Variables that require batching
        variables = {
            'ar': ['2020', '2021', '2022', '2023'],  # 4 values > batch_size of 3
            'nyregunder': ''
        }
        
        with pytest.raises(BatchRequestError) as exc_info:
            self.client.get_data_as_dataframe(
                'test_product', variables, use_batching=True, show_progress=False
            )

        assert mock_get_data.call_count == 2
        assert exc_info.value.failed_batches == [{"batch": 2, "error": "API Error"}]
        assert len(exc_info.value.partial_result) == 1
        assert exc_info.value.partial_result.iloc[0]['ar'] == '2020'
        assert exc_info.value.partial_result.attrs['incomplete'] is True

    @patch.object(TrafikanalysClient, '_get_data')
    def test_batch_error_can_return_explicitly_marked_partial_result(self, mock_get_data):
        """Partial data requires opt-in and carries machine-readable incompleteness."""
        mock_get_data.side_effect = [
            {'Rows': [{'Cell': [
                {'Column': 'ar', 'Value': '2020'},
                {'Column': 'nyregunder', 'Value': '100'}
            ]}]},
            RuntimeError("API Error"),
        ]
        df = self.client.get_data_as_dataframe(
            'test_product', {'ar': ['2020', '2021', '2022', '2023'], 'nyregunder': ''},
            use_batching=True, show_progress=False, allow_partial=True
        )

        assert len(df) == 1
        assert df.attrs['incomplete'] is True
        assert df.attrs['failed_batches'][0]['batch'] == 2

    @patch.object(TrafikanalysClient, '_get_data')
    def test_successful_empty_batches_are_a_valid_empty_selection(self, mock_get_data):
        mock_get_data.return_value = {'Rows': []}
        df = self.client.get_data_as_dataframe(
            'test_product', {'ar': ['2020', '2021', '2022', '2023'], 'nyregunder': ''},
            use_batching=True, show_progress=False
        )

        assert df.empty
        assert df.attrs.get('incomplete', False) is False
    
    @patch.object(TrafikanalysClient, '_get_data')
    def test_duplicate_removal_in_batches(self, mock_get_data):
        """Test that duplicate rows are removed when combining batches."""
        # Mock responses with overlapping data
        mock_response_1 = {
            'Rows': [
                {'Cell': [
                    {'Column': 'ar', 'Value': '2020'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '100'}
                ]},
                {'Cell': [
                    {'Column': 'ar', 'Value': '2021'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '110'}
                ]}
            ]
        }
        
        # Second response has duplicate of first row
        mock_response_2 = {
            'Rows': [
                {'Cell': [
                    {'Column': 'ar', 'Value': '2020'},  # Duplicate
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '100'}
                ]},
                {'Cell': [
                    {'Column': 'ar', 'Value': '2022'},
                    {'Column': 'reglan', 'Value': '01'},
                    {'Column': 'nyregunder', 'Value': '120'}
                ]}
            ]
        }
        
        mock_get_data.side_effect = [mock_response_1, mock_response_2]
        
        # Variables that require batching
        variables = {
            'ar': ['2020', '2021', '2022', '2023'],
            'reglan': ['01'],
            'nyregunder': ''
        }
        
        # Get data with batching
        df = self.client.get_data_as_dataframe(
            'test_product', 
            variables, 
            use_batching=True,
            show_progress=False
        )
        
        # Should have 3 unique rows (duplicate removed)
        assert len(df) == 3
        assert len(df['ar'].unique()) == 3  # 2020, 2021, 2022
    
    def test_progress_messages(self, capsys):
        """Test that progress messages are shown correctly."""
        with patch.object(self.client, '_get_data') as mock_get_data:
            # Mock with actual data to get successful completion message
            mock_response = {
                'Rows': [
                    {'Cell': [
                        {'Column': 'ar', 'Value': '2020'},
                        {'Column': 'nyregunder', 'Value': '100'}
                    ]}
                ]
            }
            mock_get_data.return_value = mock_response
            
            variables = {
                'ar': ['2020', '2021', '2022', '2023'],  # Requires batching
                'nyregunder': ''
            }
            
            # Test with progress enabled
            self.client.get_data_as_dataframe(
                'test_product',
                variables,
                use_batching=True,
                show_progress=True
            )
            
            captured = capsys.readouterr()
            assert "Large query detected" in captured.out
            assert "Processing batch" in captured.out
            assert "Batch processing complete" in captured.out
    
    def test_progress_messages_no_data(self, capsys):
        """Test progress messages when no data is returned."""
        with patch.object(self.client, '_get_data') as mock_get_data:
            mock_get_data.return_value = {'Rows': []}  # Empty response
            
            variables = {
                'ar': ['2020', '2021', '2022', '2023'],  # Requires batching
                'nyregunder': ''
            }
            
            # Test with progress enabled
            self.client.get_data_as_dataframe(
                'test_product',
                variables,
                use_batching=True,
                show_progress=True
            )
            
            captured = capsys.readouterr()
            assert "Large query detected" in captured.out
            assert "Processing batch" in captured.out
            assert "No data returned from any batch" in captured.out


class TestBatchingEdgeCases:
    """Test edge cases and boundary conditions for batching."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TrafikanalysClient(
            cache_enabled=False,
            rate_limit_enabled=False,
            max_batch_size=5,
            debug=False
        )
    
    def test_empty_variables(self):
        """Test batching with empty variables."""
        variables = {}
        batches = self.client._create_batches(variables, show_progress=False)
        
        assert len(batches) == 1
        assert batches[0] == {}
    
    def test_single_value_variables(self):
        """Test batching with single values that don't need batching."""
        variables = {
            'ar': '2020',  # Single string value
            'reglan': ['01'],  # Single item list
            'nyregunder': ''  # Empty string
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        assert len(batches) == 1
        assert batches[0] == variables
    
    def test_exact_batch_size_boundary(self):
        """Test variables that are exactly at the batch size boundary."""
        # Exactly max_batch_size values - should NOT need batching
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024'],  # Exactly 5 values
            'nyregunder': ''
        }
        
        assert not self.client._needs_batching(variables)
        
        batches = self.client._create_batches(variables, show_progress=False)
        assert len(batches) == 1
        
        # One more value - should need batching
        variables['ar'].append('2025')  # Now 6 values
        
        assert self.client._needs_batching(variables)
        
        batches = self.client._create_batches(variables, show_progress=False)
        assert len(batches) == 2
    
    def test_very_large_variable(self):
        """Test batching with very large number of values."""
        # Create a variable with many values
        large_years = [str(year) for year in range(2000, 2030)]  # 30 years
        
        variables = {
            'ar': large_years,
            'nyregunder': ''
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        # Should create 6 batches (5*5 + 5 values)
        assert len(batches) == 6
        
        # Check that all years are included across batches
        all_years = []
        for batch in batches:
            all_years.extend(batch['ar'])
        
        assert len(all_years) == 30
        assert set(all_years) == set(large_years)
    
    def test_build_query_string_for_batches(self):
        """Test that query strings are built correctly for batches."""
        variables = {
            'ar': ['2020', '2021', '2022', '2023', '2024', '2025'],  # 6 values
            'reglan': ['01'],
            'nyregunder': ''
        }
        
        batches = self.client._create_batches(variables, show_progress=False)
        
        # Build query strings for each batch
        queries = []
        for batch in batches:
            query = self.client._build_query('test_product', batch)
            queries.append(query)
        
        # Should have 2 query strings
        assert len(queries) == 2
        
        # First query should have years 2020-2024
        assert 'ar:2020,2021,2022,2023,2024' in queries[0]
        assert 'reglan:01' in queries[0]
        assert 'nyregunder' in queries[0]
        
        # Second query should have year 2025
        assert 'ar:2025' in queries[1]
        assert 'reglan:01' in queries[1]
        assert 'nyregunder' in queries[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
