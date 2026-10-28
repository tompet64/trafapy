import requests
import pandas as pd
import logging
import time
from typing import Dict, List, Union, Optional, Any
from functools import wraps
from itertools import product
import math

from .cache_utils import APICache, cached_api_request, DEFAULT_CACHE_DIR

logger = logging.getLogger(__name__)


class APIResponseError(RuntimeError):
    """Raised when the Trafikanalys API returns an unsuccessful response."""


class BatchRequestError(RuntimeError):
    """Raised when one or more batches fail and a complete result is unavailable."""

    def __init__(self, message: str, partial_result: Optional[pd.DataFrame] = None,
                 failed_batches: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.partial_result = partial_result
        self.failed_batches = failed_batches or []
        if self.partial_result is not None:
            self.partial_result.attrs["incomplete"] = True
            self.partial_result.attrs["failed_batches"] = self.failed_batches

def rate_limit(calls_per_second: float = 1.0):
    """
    Decorator to rate limit function calls.
    
    Args:
        calls_per_second: Maximum number of calls per second allowed
    """
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                if len(args) > 0 and hasattr(args[0], 'debug') and args[0].debug:
                    print(f"Rate limiting: waiting {left_to_wait:.2f} seconds")
                time.sleep(left_to_wait)
            
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return wrapper
    return decorator


class RateLimiter:
    """
    Advanced rate limiter with burst support and backoff strategies.
    """
    
    def __init__(self, calls_per_second: float = 1.0, burst_size: int = 5, 
                 backoff_factor: float = 2.0, max_retries: int = 3):
        """
        Initialize rate limiter.
        
        Args:
            calls_per_second: Base rate limit (calls per second)
            burst_size: Number of calls allowed in a burst
            backoff_factor: Exponential backoff multiplier for retries
            max_retries: Maximum number of retry attempts
        """
        self.calls_per_second = calls_per_second
        self.burst_size = burst_size
        self.backoff_factor = backoff_factor
        self.max_retries = max_retries
        
        # Sliding window for burst control
        self.call_times = []
        self.min_interval = 1.0 / calls_per_second
        
    def wait_if_needed(self, debug: bool = False):
        """
        Wait if rate limit would be exceeded.
        
        Args:
            debug: Whether to print debug information
        """
        current_time = time.time()
        
        # Clean old calls (older than 1 second for burst window)
        self.call_times = [t for t in self.call_times if current_time - t < 1.0]
        
        # Check burst limit
        if len(self.call_times) >= self.burst_size:
            sleep_time = 1.0 - (current_time - self.call_times[0])
            if sleep_time > 0:
                if debug:
                    print(f"Burst limit reached: waiting {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                current_time = time.time()
        
        # Check base rate limit
        if self.call_times:
            time_since_last = current_time - self.call_times[-1]
            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                if debug:
                    print(f"Rate limit: waiting {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                current_time = time.time()
        
        # Record this call
        self.call_times.append(current_time)
    
    def execute_with_retry(self, func, *args, debug: bool = False, **kwargs):
        """
        Execute a function with rate limiting and exponential backoff retry.
        
        Args:
            func: Function to execute
            *args: Function arguments
            debug: Whether to print debug information
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If all retries are exhausted
        """
        for attempt in range(self.max_retries + 1):
            try:
                self.wait_if_needed(debug)
                return func(*args, **kwargs)
                
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries:
                    raise e
                
                # Check if it's a rate limit error (HTTP 429)
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 429:
                        # Rate limited - wait longer
                        wait_time = (self.backoff_factor ** attempt) * 2
                        if debug:
                            print(f"Rate limited (HTTP 429): waiting {wait_time:.2f} seconds before retry {attempt + 1}")
                        time.sleep(wait_time)
                        continue
                    elif e.response.status_code >= 500:
                        # Server error - retry with backoff
                        wait_time = self.backoff_factor ** attempt
                        if debug:
                            print(f"Server error ({e.response.status_code}): waiting {wait_time:.2f} seconds before retry {attempt + 1}")
                        time.sleep(wait_time)
                        continue
                
                # For other errors, re-raise immediately
                raise e


class TrafikanalysClient:
    """
    Simplified client for the Trafikanalys API focused on retrieving data using known queries.
    Includes rate limiting capabilities and automatic batching for large queries.
    """
    
    BASE_URL = "https://api.trafa.se/api"
    
    def __init__(self, language: str = "sv", debug: bool = False, 
                 cache_enabled: bool = False, cache_dir: str = DEFAULT_CACHE_DIR,
                 cache_expiry_seconds: int = 1800,  # Default: 30 minutes
                 rate_limit_enabled: bool = True, calls_per_second: float = 1.0,
                 burst_size: int = 5, enable_retry: bool = True,
                 max_batch_size: int = 50):
        """
        Initialize the client.
        
        Args:
            language: Language for responses, 'sv' for Swedish or 'en' for English
            debug: Whether to print debug information
            cache_enabled: Whether to use caching
            cache_dir: Directory to store cache files
            cache_expiry_seconds: Cache expiry time in seconds
            rate_limit_enabled: Whether to enable rate limiting
            calls_per_second: Maximum API calls per second
            burst_size: Number of calls allowed in a burst
            enable_retry: Whether to enable automatic retries with backoff
            max_batch_size: Maximum number of values per variable in a single request
        """
        self.language = language
        self.debug = debug
        self.session = requests.Session()
        self.max_batch_size = max_batch_size
        self.cache = APICache(
            cache_dir=cache_dir,
            expiry_seconds=cache_expiry_seconds,
            enabled=cache_enabled
        )
        
        # Rate limiting configuration
        self.rate_limit_enabled = rate_limit_enabled
        if rate_limit_enabled:
            self.rate_limiter = RateLimiter(
                calls_per_second=calls_per_second,
                burst_size=burst_size,
                max_retries=3 if enable_retry else 0
            )
        else:
            self.rate_limiter = None
    
    def _make_request_raw(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make an HTTP request without rate limiting (internal use).
        
        Args:
            url: Request URL
            params: Request parameters
            
        Returns:
            Response JSON data
        """
        response = self.session.get(url, params=params)
        
        if response.status_code != 200:
            if self.debug:
                print(f"Request failed with status code {response.status_code}")
                print(f"Response text: {response.text}")
            
            # Raise exception for rate limiter to handle
            if response.status_code == 429:
                raise requests.exceptions.RequestException(f"Rate limited (HTTP 429)", response=response)
            elif response.status_code >= 500:
                raise requests.exceptions.RequestException(f"Server error ({response.status_code})", response=response)

            raise APIResponseError(
                f"Trafikanalys API request failed with HTTP {response.status_code}"
            )

        data = response.json()
        self._validate_api_response(data)
        return data

    @staticmethod
    def _validate_api_response(data: Any) -> Dict[str, Any]:
        """Reject API-level errors before they can be used or cached as data."""
        if not isinstance(data, dict):
            raise APIResponseError("Trafikanalys API response must be a JSON object")
        errors = data.get("Errors")
        if errors:
            raise APIResponseError(f"Trafikanalys API reported errors: {errors!r}")
        return data
    
    def _make_request(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make an HTTP request with rate limiting and retry logic.
        
        Args:
            url: Request URL
            params: Request parameters
            
        Returns:
            Response JSON data
        """
        if self.rate_limit_enabled and self.rate_limiter:
            return self.rate_limiter.execute_with_retry(
                self._make_request_raw, url, params, debug=self.debug
            )
        else:
            return self._make_request_raw(url, params)
    
    def configure_rate_limiting(self, enabled: bool = True, calls_per_second: float = 1.0,
                              burst_size: int = 5, enable_retry: bool = True):
        """
        Configure rate limiting settings.
        
        Args:
            enabled: Whether to enable rate limiting
            calls_per_second: Maximum API calls per second
            burst_size: Number of calls allowed in a burst
            enable_retry: Whether to enable automatic retries with backoff
        """
        self.rate_limit_enabled = enabled
        if enabled:
            self.rate_limiter = RateLimiter(
                calls_per_second=calls_per_second,
                burst_size=burst_size,
                max_retries=3 if enable_retry else 0
            )
            if self.debug:
                print(f"Rate limiting configured: {calls_per_second} calls/sec, burst={burst_size}, retry={enable_retry}")
        else:
            self.rate_limiter = None
            if self.debug:
                print("Rate limiting disabled")
    
    def configure_batching(self, max_batch_size: int = 50):
        """
        Configure batching settings.
        
        Args:
            max_batch_size: Maximum number of values per variable in a single request
        """
        self.max_batch_size = max_batch_size
        if self.debug:
            print(f"Batching configured: max {max_batch_size} values per variable")
    
    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limiting configuration.
        
        Returns:
            Dictionary with rate limiting information
        """
        if not self.rate_limit_enabled or not self.rate_limiter:
            return {
                "enabled": False,
                "calls_per_second": 0,
                "burst_size": 0,
                "recent_calls": 0
            }
        
        return {
            "enabled": True,
            "calls_per_second": self.rate_limiter.calls_per_second,
            "burst_size": self.rate_limiter.burst_size,
            "recent_calls": len(self.rate_limiter.call_times),
            "backoff_factor": self.rate_limiter.backoff_factor,
            "max_retries": self.rate_limiter.max_retries
        }
    
    def get_batching_info(self) -> Dict[str, Any]:
        """
        Get current batching configuration.
        
        Returns:
            Dictionary with batching information
        """
        return {
            "max_batch_size": self.max_batch_size
        }
     
    def list_products(self) -> pd.DataFrame:
        """
        List all available products.
        
        Returns:
            DataFrame with product information
        """
        url = f"{self.BASE_URL}/structure"
        
        # Use cached request
        data = cached_api_request(
            cache=self.cache,
            request_func=self._make_request,
            url=url,
            params={"lang": self.language},
            debug=self.debug
        )
        
        if not data or 'StructureItems' not in data:
            if self.debug:
                print("No products found in response")
            return pd.DataFrame()
        
        products = data['StructureItems']
        
        product_data = []
        for product in products:
            product_data.append({
                'code': product.get('Name', ''),
                'label': product.get('Label', ''),
                'description': product.get('Description', ''),
                'id': product.get('Id', ''),
                'unique_id': product.get('UniqueId', ''),
                'active_from': product.get('ActiveFrom', '')
            })
        
        return pd.DataFrame(product_data)
    
    def search_products(self, search_term):
        """
        Search for products in the Trafikanalys API.
    
        Args:
            search_term: Term to search for
            language: Language for responses, 'sv' for Swedish or 'en' for English
            debug: Whether to print debug information
        
        Returns:
            DataFrame with matching products
        """
        products = self.list_products()
    
        if products.empty:
            return products
    
        # Search in label and description
        search_term = search_term.lower()
        mask = (
            products['label'].str.lower().str.contains(search_term, na=False) | 
            products['description'].str.lower().str.contains(search_term, na=False)
        )
    
        return products[mask]
    
    def _build_query(self, product_code: str, variables: Dict[str, Union[str, List[str]]]) -> str:
        """
        Build a query string for the API.
        
        Args:
            product_code: The product code (e.g., "t10016")
            variables: Dictionary of variables and values (e.g., {"ar": ["2020", "2021"]})
            
        Returns:
            Query string
        """
        query_parts = [product_code]
        
        for var_name, var_values in variables.items():
            if isinstance(var_values, list) and var_values:
                # Multiple values
                values_str = ",".join(str(v) for v in var_values)
                query_parts.append(f"{var_name}:{values_str}")
            elif var_values:
                # Single value
                query_parts.append(f"{var_name}:{var_values}")
            else:
                # No filter, just include the variable
                query_parts.append(var_name)
        
        return "|".join(query_parts)
    
    def _needs_batching(self, variables: Dict[str, Union[str, List[str]]]) -> bool:
        """
        Check if a query needs batching based on the number of values per variable.
        
        Args:
            variables: Dictionary of variables and values
            
        Returns:
            True if batching is needed, False otherwise
        """
        # Check if any variable has more values than max_batch_size
        for var_name, var_values in variables.items():
            if isinstance(var_values, list) and len(var_values) > self.max_batch_size:
                return True
                
        return False
    
    def _create_batches(self, variables: Dict[str, Union[str, List[str]]], 
                       show_progress: bool = None) -> List[Dict[str, Union[str, List[str]]]]:
        """
        Create batches from variables to avoid URL length limits by splitting variables 
        that have more than max_batch_size values.
        
        Args:
            variables: Dictionary of variables and values
            show_progress: Whether to show progress (defaults to debug mode setting)
            
        Returns:
            List of variable dictionaries for batched requests
        """
        if show_progress is None:
            show_progress = self.debug
            
        # Find variables that need batching (have more than max_batch_size values)
        variables_to_batch = []
        for var_name, var_values in variables.items():
            if isinstance(var_values, list) and len(var_values) > self.max_batch_size:
                variables_to_batch.append((var_name, len(var_values)))
        
        if not variables_to_batch:
            return [variables]
        
        # Sort by size (largest first) to batch the most problematic variable
        variables_to_batch.sort(key=lambda x: x[1], reverse=True)
        batch_var_name, batch_var_size = variables_to_batch[0]
        
        if show_progress:
            print(f"  📋 Batching variable '{batch_var_name}' ({batch_var_size} values)")
            if len(variables_to_batch) > 1:
                other_vars = [f"{name}({size})" for name, size in variables_to_batch[1:]]
                print(f"  ℹ️  Other large variables will be included in all batches: {', '.join(other_vars)}")
        
        # Create batches by splitting the largest variable
        batch_values = variables[batch_var_name]
        batches = []
        
        for i in range(0, len(batch_values), self.max_batch_size):
            batch_vars = variables.copy()
            batch_vars[batch_var_name] = batch_values[i:i + self.max_batch_size]
            batches.append(batch_vars)
        
        if show_progress and batches:
            print(f"  ✅ Created {len(batches)} batches (max {self.max_batch_size} values per variable)")
            
            # Show sample of first batch
            if len(batches) > 0:
                first_batch = batches[0]
                batch_summary = []
                for k, v in first_batch.items():
                    if isinstance(v, list):
                        batch_summary.append(f"{k}({len(v)})")
                    else:
                        batch_summary.append(f"{k}")
                print(f"  📊 Example batch structure: {', '.join(batch_summary)}")
        
        return batches if batches else [variables]
    
    def _get_data(self, query: str) -> Dict[str, Any]:
        """
        Get data from the API.
        
        Args:
            query: Query string
            
        Returns:
            API response data
        """
        url = f"{self.BASE_URL}/data"
        
        if self.debug:
            print(f"Making request to: {url}?query={query}&lang={self.language}")
        
        # Use cached request
        data = cached_api_request(
            cache=self.cache,
            request_func=self._make_request,
            url=url,
            params={"query": query, "lang": self.language},
            debug=self.debug
        )

        # Also validate cache hits: a bad response written by an older client
        # must not become a statistical result after upgrading.
        data = self._validate_api_response(data)
        
        if self.debug and 'Rows' in data:
            print(f"Got {len(data['Rows'])} rows from API")
            
            # Print column information if available
            if 'Header' in data and 'Column' in data['Header']:
                columns = data['Header']['Column']
                print(f"Found {len(columns)} columns in response")
                for col in columns[:5]:  # Show first 5 columns
                    print(f"  - {col.get('Name')}: {col.get('Value')} ({col.get('Type')})")
                
                if len(columns) > 5:
                    print(f"  - ... and {len(columns) - 5} more columns")
            
        return data
    
    def _get_structure(self, query: str = "") -> Dict[str, Any]:
        """
        Get structure information from the API.
        
        Args:
            query: Query string (optional)
            
        Returns:
            API response data
        """
        url = f"{self.BASE_URL}/structure"
        params = {"lang": self.language}
        
        if query:
            params["query"] = query
        
        if self.debug:
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            print(f"Making request to: {url}?{param_str}")
        
        # Use cached request
        return cached_api_request(
            cache=self.cache,
            request_func=self._make_request,
            url=url,
            params=params,
            debug=self.debug
        )
    
    def _process_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a row from the API response.
        
        Args:
            row: API response row
            
        Returns:
            Processed row data
        """
        processed = {}
        
        if 'Cell' in row:
            cells = row['Cell']
            
            if isinstance(cells, list):
                for cell in cells:
                    if isinstance(cell, dict):
                        col_name = cell.get('Column')
                        value = cell.get('Value')
                        
                        if col_name:
                            processed[col_name] = value
            elif isinstance(cells, dict):
                col_name = cells.get('Column')
                value = cells.get('Value')
                
                if col_name:
                    processed[col_name] = value
        
        return processed
    
    def _data_to_dataframe(self, data: Dict[str, Any]) -> pd.DataFrame:
        """
        Convert API data to a DataFrame.
        
        Args:
            data: API response data
            
        Returns:
            DataFrame with the data
        """
        if not data or 'Rows' not in data or not data['Rows']:
            if self.debug:
                print("No rows in data")
            return pd.DataFrame()
        
        rows = data['Rows']
        
        if self.debug:
            print(f"Processing {len(rows)} rows")
            
        processed_rows = [self._process_row(row) for row in rows]
        
        # Filter out empty rows
        processed_rows = [row for row in processed_rows if row]
        
        if self.debug:
            print(f"Processed {len(processed_rows)} rows")
            if processed_rows:
                print(f"Columns in first row: {list(processed_rows[0].keys())}")
        
        return pd.DataFrame(processed_rows)
    
    def get_data_as_dataframe(self, product_code: str, variables: Dict[str, Union[str, List[str]]], 
                            use_batching: bool = True, show_progress: bool = True,
                            allow_partial: bool = False) -> pd.DataFrame:
        """
        Get data from the API as a DataFrame with automatic batching for large queries.
        
        Args:
            product_code: The product code (e.g., "t10016")
            variables: Dictionary of variables and values (e.g., {"ar": ["2020", "2021"]})
            use_batching: Whether to use automatic batching for large queries
            show_progress: Whether to show progress messages (True by default, can be overridden by debug mode)
            allow_partial: If True, return successful batches after failures and mark the
                DataFrame with ``attrs['incomplete']`` and ``attrs['failed_batches']``.
            
        Returns:
            DataFrame with the data
        """
        if use_batching and self._needs_batching(variables):
            batches = self._create_batches(variables, show_progress=(show_progress or self.debug))
            
            # Show initial batching message
            if show_progress or self.debug:
                print(f"📊 Large query detected - retrieving data in {len(batches)} batches...")
            
            all_dataframes = []
            failed_batches = []
            
            for i, batch_vars in enumerate(batches):
                batch_num = i + 1
                
                # Show progress for each batch
                if show_progress or self.debug:
                    print(f"  🔄 Processing batch {batch_num}/{len(batches)}...", end="")
                
                try:
                    query = self._build_query(product_code, batch_vars)
                    data = self._get_data(query)
                    df = self._data_to_dataframe(data)
                    
                    if not df.empty:
                        all_dataframes.append(df)
                        batch_rows = len(df)
                        if show_progress or self.debug:
                            print(f" ✅ {batch_rows:,} rows")
                    else:
                        if show_progress or self.debug:
                            print(" ⚠️  No data")
                        elif self.debug:
                            print(f"Batch {batch_num} returned no data")
                            
                except Exception as e:
                    failed_batches.append({"batch": batch_num, "error": str(e)})
                    if show_progress or self.debug:
                        print(f" ❌ Error: {str(e)[:50]}...")
                    elif self.debug:
                        print(f"Batch {batch_num} failed: {e}")
                    continue
            
            if not all_dataframes and not failed_batches:
                if show_progress or self.debug:
                    print("❌ No data returned from any batch")
                return pd.DataFrame()
            
            # Combine all dataframes
            if show_progress or self.debug:
                print(f"  🔗 Combining data from {len(all_dataframes)} successful batches...", end="")
            
            result_df = (pd.concat(all_dataframes, ignore_index=True)
                         if all_dataframes else pd.DataFrame())
            
            # Remove duplicates that might occur due to overlapping batches
            initial_rows = len(result_df)
            result_df = result_df.drop_duplicates()
            final_rows = len(result_df)
            
            # Show completion message
            if show_progress or self.debug:
                print(" ✅" if not failed_batches else " ⚠️")
                if initial_rows != final_rows:
                    print(f"  🧹 Removed {initial_rows - final_rows:,} duplicate rows")
                if failed_batches:
                    print(
                        f"⚠️ Batch processing incomplete: {len(failed_batches)} of "
                        f"{len(batches)} batches failed; {final_rows:,} rows collected"
                    )
                else:
                    print(f"✅ Batch processing complete! Retrieved {final_rows:,} total rows")
            elif self.debug:
                print(f"Combined {len(batches)} batches into {final_rows} total rows")
            
            if failed_batches:
                if not allow_partial:
                    raise BatchRequestError(
                        f"{len(failed_batches)} of {len(batches)} data batches failed; "
                        "refusing to return an incomplete result",
                        partial_result=result_df,
                        failed_batches=failed_batches,
                    )
                result_df.attrs["incomplete"] = True
                result_df.attrs["failed_batches"] = failed_batches
            else:
                result_df.attrs["incomplete"] = False

            return result_df
        
        else:
            # Standard single request
            if show_progress and not self.debug:
                print("📊 Retrieving data...", end="")
            
            query = self._build_query(product_code, variables)
            
            if self.debug:
                print(f"Query: {query}")
            
            data = self._get_data(query)
            result_df = self._data_to_dataframe(data)
            
            if show_progress and not self.debug:
                if not result_df.empty:
                    print(f" ✅ {len(result_df):,} rows")
                else:
                    print(" ⚠️  No data found")
            
            return result_df
    
    def clear_cache(self, older_than_seconds: Optional[int] = None) -> int:
        """
        Clear the cache.
        
        Args:
            older_than_seconds: Only clear files older than this many seconds
            
        Returns:
            Number of files deleted
        """
        return self.cache.clear_cache(older_than_seconds)
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about the cache.
        
        Returns:
            Dictionary with cache information
        """
        return self.cache.get_cache_info()
    


    """
    Functions for exploring variables and filter options in the Trafikanalys API.
    """ 

    def explore_product_variables(self, product_code: str) -> pd.DataFrame:
        """
        Explore the available variables for a product code in the Trafikanalys API.
        
        Args:
            product_code: The product code (e.g., "t10011")
            
        Returns:
            DataFrame with variable information (name, label, type, description)
        """
        # Use cached request through the API structure
        data = self._get_structure(query=product_code)
        
        if self.debug:
            print(f"API response structure: {list(data.keys())}")
        
        # Extract variables from the structure
        variables = []
        
        if 'StructureItems' not in data:
            if self.debug:
                print("No 'StructureItems' in API response")
            return pd.DataFrame()
        
        def process_item(item, parent_hierarchy=None):
            """Process an item and its children recursively."""
            item_type = item.get('Type', '')
            item_name = item.get('Name', '')
            
            # Process depending on type
            if item_type == 'D':  # Variable
                variables.append({
                    'name': item_name,
                    'label': item.get('Label', ''),
                    'type': 'Variable',
                    'description': item.get('Description', ''),
                    'data_type': item.get('DataType', ''),
                    'has_filter_options': True,
                    'parent_hierarchy': parent_hierarchy
                })
            elif item_type == 'M':  # Measure
                variables.append({
                    'name': item_name,
                    'label': item.get('Label', ''),
                    'type': 'Measure',
                    'description': item.get('Description', ''),
                    'data_type': item.get('DataType', ''),
                    'has_filter_options': False,
                    'parent_hierarchy': parent_hierarchy
                })
            elif item_type == 'H':  # Hierarchy
                # Add the hierarchy itself as a "group" type
                variables.append({
                    'name': item_name,
                    'label': item.get('Label', ''),
                    'type': 'Hierarchy',
                    'description': item.get('Description', ''),
                    'data_type': item.get('DataType', ''),
                    'has_filter_options': False,
                    'parent_hierarchy': parent_hierarchy
                })
                
                # Process children of the hierarchy
                if 'StructureItems' in item and item['StructureItems']:
                    for child_item in item['StructureItems']:
                        process_item(child_item, item_name)  # Pass current hierarchy as parent
        
        # Process both cases: When items are inside the product and when they're at top level
        for item in data['StructureItems']:
            # Check if this is our product
            if item.get('Name') == product_code and item.get('Type') == 'P':
                if self.debug:
                    print(f"Found product: {item.get('Label')}")
                
                # Look for variables inside the product
                if 'StructureItems' in item and item['StructureItems']:
                    for var_item in item['StructureItems']:
                        process_item(var_item)
                        
            # Also check for variables at top level (with our product code as parent)
            elif item.get('ParentName') == product_code:
                process_item(item)
        
        if not variables and self.debug:
            print("No variables found for this product")
            
            # Print some details about what we found to help diagnose
            print(f"Total StructureItems: {len(data['StructureItems'])}")
            for idx, item in enumerate(data['StructureItems'][:5]):  # Show first 5 items
                print(f"Item {idx}: Name={item.get('Name')}, Type={item.get('Type')}, ParentName={item.get('ParentName')}")
        
        return pd.DataFrame(variables)


    def explore_variable_options(self, product_code: str, variable_name: str) -> pd.DataFrame:
        """
        Explore the available filter options for a variable in a product.
        
        Args:
            product_code: The product code (e.g., "t10011")
            variable_name: The variable name (e.g., "ar" for year)
            
        Returns:
            DataFrame with filter options (name, label, description)
        """
        # First try direct access to the variable (this works for most variables including those in hierarchies)
        direct_query = f"{product_code}|{variable_name}"
        
        # Get the structure for the product + variable directly
        url = f"{self.BASE_URL}/structure"
        params = {"query": direct_query, "lang": self.language}
        
        if self.debug:
            print(f"Making request to: {url}?query={direct_query}&lang={self.language}")
            
        # Use cached request
        data = cached_api_request(
            cache=self.cache,
            request_func=self._make_request,
            url=url,
            params=params,
            debug=self.debug
        )
        
        # Extract filter options from the structure
        filter_options = []
        
        if 'StructureItems' not in data:
            if self.debug:
                print("No 'StructureItems' in direct API response, trying hierarchical approach")
            # If direct access fails, try the hierarchical approach
            return self._explore_variable_options_hierarchical(product_code, variable_name)
        
        # First, try to find the variable in the top-level items
        variable_found = False
        
        for item in data['StructureItems']:
            if item.get('Name') == variable_name:
                variable_found = True
                if self.debug:
                    print(f"Found variable: {item.get('Label')}")
                
                if 'StructureItems' in item and item['StructureItems']:
                    self._process_filter_options(item['StructureItems'], filter_options)
                break
        
        # If not found in top-level, search inside the product item and hierarchies
        if not variable_found:
            # Recursive function to find variable in nested structure
            def find_variable(items):
                for item in items:
                    if item.get('Name') == variable_name:
                        if self.debug:
                            print(f"Found variable: {item.get('Label')}")
                        
                        if 'StructureItems' in item and item['StructureItems']:
                            self._process_filter_options(item['StructureItems'], filter_options)
                        return True
                    
                    # Look in children
                    if 'StructureItems' in item and item['StructureItems']:
                        if find_variable(item['StructureItems']):
                            return True
                
                return False
            
            for item in data['StructureItems']:
                if 'StructureItems' in item and item['StructureItems']:
                    if find_variable(item['StructureItems']):
                        variable_found = True
                        break
        
        if not variable_found:
            if self.debug:
                print(f"Variable {variable_name} not found in direct API response, trying hierarchical approach")
            # If variable not found with direct approach, try hierarchical
            return self._explore_variable_options_hierarchical(product_code, variable_name)
        
        if not filter_options and self.debug:
            print("No filter options found for this variable")
        
        return pd.DataFrame(filter_options)


    def _process_filter_options(self, items: List[Dict], filter_options: List[Dict]) -> None:
        """
        Process filter option items and add them to the filter_options list.
        
        Args:
            items: List of filter option items
            filter_options: List to add filter options to
        """
        for option in items:
            if option.get('Type') in ['DV', 'F']:  # DV = variable value, F = filter
                filter_options.append({
                    'name': option.get('Name', ''),
                    'label': option.get('Label', ''),
                    'description': option.get('Description', ''),
                    'option_type': 'Filter' if option.get('Type') == 'F' else 'Value',
                    'unique_id': option.get('UniqueId', '')
                })

    def preview_query(self, product_code: str, query_dict: Dict[str, Any]) -> str:
        """
        Preview the API query that would be generated from the provided parameters.
        
        Args:
            product_code: The product code (e.g., "t10011")
            query_dict: Dictionary with selected variables and filters
            
        Returns:
            The API query string
        """
        query = self._build_query(product_code, query_dict)
        
        print(f"\nAPI Query Preview:")
        print(f"https://api.trafa.se/api/data?query={query}")
        
        # Check if batching would be needed
        if self._needs_batching(query_dict):
            batches = self._create_batches(query_dict)
            print(f"\nNote: This query will be split into {len(batches)} batches due to size")
        
        return query
    
    def _explore_variable_options_hierarchical(self, product_code: str, variable_name: str) -> pd.DataFrame:
        """
        Explore variable options using a hierarchical approach as fallback.
        
        Args:
            product_code: The product code
            variable_name: The variable name
            
        Returns:
            DataFrame with filter options
        """
        # First, check if this is part of a hierarchy by getting the product structure
        data = self._get_structure(query=product_code)
        
        # Find hierarchy path to the variable
        hierarchy_path = None
        
        def find_variable_in_structure(items, parent_path=None):
            """Find a variable in the structure and return its hierarchy path."""
            path = parent_path[:] if parent_path else []
            
            for item in items:
                item_type = item.get('Type', '')
                item_name = item.get('Name', '')
                
                if item_name == variable_name and item_type in ['D', 'M']:
                    return path
                
                if item_type == 'H':
                    # Add this hierarchy to the path
                    new_path = path + [item_name]
                    
                    # Look in children
                    if 'StructureItems' in item and item['StructureItems']:
                        result = find_variable_in_structure(item['StructureItems'], new_path)
                        if result:
                            return result
            
            return None
        
        if 'StructureItems' in data:
            for item in data['StructureItems']:
                if item.get('Type') == 'P' and item.get('Name') == product_code:
                    if 'StructureItems' in item and item['StructureItems']:
                        hierarchy_path = find_variable_in_structure(item['StructureItems'])
        
        if not hierarchy_path:
            if self.debug:
                print(f"No hierarchy path found for variable {variable_name}")
            return pd.DataFrame()
        
        # Build the query string based on hierarchy path
        query = product_code
        for h in hierarchy_path:
            query += f"|{h}"
        query += f"|{variable_name}"
        
        if self.debug:
            print(f"Using hierarchical query: {query}")
        
        # Get the structure for the product + hierarchy + variable
        url = f"{self.BASE_URL}/structure"
        params = {"query": query, "lang": self.language}
        
        # Use cached request
        data = cached_api_request(
            cache=self.cache,
            request_func=self._make_request,
            url=url,
            params=params,
            debug=self.debug
        )
        
        # Extract filter options from the structure
        filter_options = []
        
        if 'StructureItems' not in data:
            if self.debug:
                print("No 'StructureItems' in hierarchical API response")
            return pd.DataFrame()
        
        # First, try to find the variable in the top-level items
        variable_found = False
        
        for item in data['StructureItems']:
            if item.get('Name') == variable_name:
                variable_found = True
                if self.debug:
                    print(f"Found variable in hierarchical response: {item.get('Label')}")
                
                if 'StructureItems' in item and item['StructureItems']:
                    self._process_filter_options(item['StructureItems'], filter_options)
                break
        
        # If not found in top-level, search recursively
        if not variable_found:
            def find_variable(items):
                for item in items:
                    if item.get('Name') == variable_name:
                        if self.debug:
                            print(f"Found variable in hierarchical response: {item.get('Label')}")
                        
                        if 'StructureItems' in item and item['StructureItems']:
                            self._process_filter_options(item['StructureItems'], filter_options)
                        return True
                    
                    # Look in children
                    if 'StructureItems' in item and item['StructureItems']:
                        if find_variable(item['StructureItems']):
                            return True
                
                return False
            
            for item in data['StructureItems']:
                if 'StructureItems' in item and item['StructureItems']:
                    if find_variable(item['StructureItems']):
                        variable_found = True
                        break
        
        if not variable_found and self.debug:
            print(f"Variable {variable_name} not found in hierarchical API response")
        
        if not filter_options and self.debug:
            print("No filter options found for this variable")
        
        return pd.DataFrame(filter_options)


    """
    Functions for automating queries for the Trafikanalys API.
    """ 

    def get_all_available_values(self, product_code: str, variable_name: str, exclude_totals: bool = True) -> List[str]:
        """
        Get all available values for any variable in a product.
        
        Args:
            product_code: The product code (e.g., "t10026")
            variable_name: The variable name (e.g., "ar", "drivmedel", "reglan")
            exclude_totals: Whether to exclude total values like 't1'
            
        Returns:
            List of available values as strings
        """
        # Get filter options for the variable
        options_df = self.explore_variable_options(product_code, variable_name)
        
        if options_df.empty:
            if self.debug:
                print(f"No options found for variable {variable_name} in product {product_code}")
            return []
        
        # Extract values
        values = []
        for _, row in options_df.iterrows():
            value_name = row['name']
            
            # Skip total values if requested
            if exclude_totals and value_name in ['t1', 'totalt', 'total']:
                continue
                
            # Skip special filter options for years
            if variable_name == 'ar' and value_name in ['senaste', 'forra']:
                continue
                
            values.append(value_name)
        
        # Sort years in ascending order if this is the year variable
        if variable_name == 'ar':
            # Filter to only numeric years and sort
            numeric_years = [year for year in values if year.isdigit() and len(year) == 4]
            numeric_years.sort()
            values = numeric_years
        
        if self.debug:
            print(f"Found {len(values)} available values for {variable_name} in {product_code}: {values}")
        
        return values

    def build_query(self, product_code: str, **kwargs) -> Dict[str, Union[str, List[str]]]:
        """
        Build a query with automated fetching of available values.
        
        Args:
            product_code: The product code
            **kwargs: Variable configurations where:
                    - key is variable name
                    - value can be:
                    - 'all': get all available values
                    - list of specific values
                    - empty string for no filter
                    - single string value
        
        Returns:
            Dictionary with query parameters
        
        Example:
            query = client.build_query(
                "t10026",
                ar='all',        # Get all available years
                drivmedel='all', # Get all fuel types
                reglan=['01'],   # Specific region
                nyregunder=''    # No filter (measure)
            )
        """
        query_dict = {}
        
        for variable_name, value_spec in kwargs.items():
            if value_spec == 'all':
                query_dict[variable_name] = self.get_all_available_values(product_code, variable_name)
            elif isinstance(value_spec, list):
                query_dict[variable_name] = value_spec
            else:
                query_dict[variable_name] = value_spec
        
        if self.debug:
            print("Built automated query:")
            for key, value in query_dict.items():
                if isinstance(value, list) and len(value) > 5:
                    print(f"  {key}: [{value[0]}, {value[1]}, ..., {value[-2]}, {value[-1]}] ({len(value)} values)")
                else:
                    print(f"  {key}: {value}")
        
        return query_dict
