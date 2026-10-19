# Testing Guide for TrafaPy

This document provides comprehensive information about testing the TrafaPy library.

## 📋 Overview

TrafaPy has a comprehensive test suite that includes:

- **Unit Tests**: Test individual components in isolation using mocks 
- **Rate Limiting Tests**: Test API rate limiting and retry mechanisms
- **Integration Tests**: Test real API interactions (use sparingly)
- **Performance Tests**: Test caching and performance optimizations
- **Error Handling Tests**: Test edge cases and error scenarios
- **Real-World Usage Tests**: Test realistic workflows and patterns

## 📁 Test Structure

```
tests/
├── __init__.py                 # Makes tests a Python package
├── conftest.py                 # Shared test fixtures and configuration
├── test_trafapy.py             # Core functionality tests
├── test_convenience.py         # Advanced features tests 
├── test_rate_limiting.py       # Rate limiting functionality tests 
├── test_batching.py            # Batching mechanism functionality tests 
└── run_tests.py                # Custom test runner script
```

## 🚀 Quick Start

### Install Test Dependencies

```bash
# Install the package and all development dependencies
python -m pip install -e ".[dev]"
```

### Run Basic Tests

```bash
# Run all unit tests (recommended for development)
pytest -m "not integration" -v

# Using the custom test runner
python tests/run_tests.py --unit --verbose

# Run with coverage reporting
pytest -m "not integration" --cov=trafapy --cov-report=term-missing

# Run rate limiting tests specifically
pytest tests/test_rate_limiting.py -v

# Run fast unit tests only (excludes performance tests)
pytest -m "not integration and not slow" -v
```

## Continuous Integration

`.github/workflows/tests.yml` runs on every push and pull request using
Python 3.10, 3.11, 3.12, and 3.13 on Ubuntu. It installs the `dev` extra from
`pyproject.toml` and runs:

```bash
python -m pytest -m "not integration" --cov=trafapy --cov-report=term-missing
```

Tests marked `integration` are excluded because they can call the live
Trafikanalys API. Mocked tests, including rate limiting and timing tests,
remain enabled. CI does not publish packages. Older Python versions listed
in the package metadata are not covered by this workflow.

## 🧪 Test Categories

### Unit Tests (Recommended for Regular Use)

Unit tests are fast, reliable, and don't require network access. They use mocking to simulate API responses.

```bash
# Run only unit tests
pytest -m "not integration" -v

# Run specific test categories
pytest -k "cache" -v              # Cache-related tests
pytest -k "client" -v             # Client functionality tests
pytest -k "query" -v              # Query building tests
pytest -k "rate_limit" -v         # Rate limiting tests
pytest -k "batching" -v           # Batching tests
pytest tests/test_rate_limiting.py -v  # All rate limiting tests

# Run specific rate limiting test classes
pytest tests/test_rate_limiting.py::TestRateLimiter -v
pytest tests/test_rate_limiting.py::TestTrafikanalysClientRateLimiting -v
```

**What they test:**
- Query building logic and parameter handling
- Batching mechanism tests
- Data processing and DataFrame conversion
- Cache functionality (save, retrieve, expire)
- Rate limiting and retry mechanisms
- Error handling and edge cases
- Utility and convenience functions
- Mock API response processing
- API call timing and burst control


### Rate Limiting Tests

Test the API rate limiting functionality to ensure responsible API usage:

```bash
# Run all rate limiting tests
pytest tests/test_rate_limiting.py -v

# Run specific rate limiting test categories
pytest tests/test_rate_limiting.py::TestRateLimiter -v           # Core rate limiter logic
pytest tests/test_rate_limiting.py::TestTrafikanalysClientRateLimiting -v  # Client integration
pytest tests/test_rate_limiting.py::TestRateLimitingEdgeCases -v # Edge cases and errors

# Run performance-sensitive rate limiting tests
pytest tests/test_rate_limiting.py::TestRateLimitingPerformance -v

# Test rate limiting with different scenarios
pytest -k "rate_limit and retry" -v      # Retry mechanism tests
pytest -k "rate_limit and burst" -v      # Burst limiting tests
```

**What they test:**
- **Rate Limiting Logic**: Ensures API calls are properly spaced
- **Burst Limiting**: Tests quick successive calls within burst limits
- **Retry Mechanisms**: Tests exponential backoff for rate limit errors (HTTP 429)
- **Server Error Handling**: Tests retry behavior for 5xx errors
- **Client Integration**: Verifies rate limiting works with TrafikanalysClient
- **Configuration**: Tests dynamic rate limit configuration
- **Edge Cases**: Tests invalid parameters and extreme scenarios
- **Performance**: Tests timing accuracy and memory usage

**Expected results:**
- ✅ All rate limiting logic functions correctly
- ⚡ Timing tests pass within tolerance (some may be slower due to actual delays)
- 🔄 Retry mechanisms work for appropriate error types
- 📊 Performance tests validate efficient operation

**Note**: Rate limiting tests include actual timing delays, so they may take longer than other unit tests (up to 30 seconds total).

### Integration Tests (Use Sparingly)

Integration tests hit the real Trafikanalys API and should be used carefully to avoid rate limiting.

```bash
# Run integration tests (use sparingly!)
pytest -m integration -v

# Run with the test runner
python tests/run_tests.py --integration
```

**What they test:**
- Real API connectivity and authentication
- Actual data retrieval and format validation
- Current API response structure

⚠️ **Important Notes:**
- May fail due to network issues, API downtime, or rate limiting
- Should not be run frequently during development
- Failures don't necessarily indicate code problems
- Use caching when running to minimize API calls

### Performance Tests

Test caching efficiency, memory usage, and concurrent access:

```bash
# Run performance-related tests
pytest -k "performance or cache" -v

# Run rate limiting performance tests
pytest tests/test_rate_limiting.py::TestRateLimitingPerformance -v

# Run tests for large datasets
pytest -k "large_dataset" -v

# Test caching performance
pytest -k "cache and performance" -v
```

## ⚙️ Test Configuration

### Pytest Configuration (`pytest.ini`)

```ini
[pytest]
testpaths = tests
markers =
    integration: marks tests as integration tests (may hit real API)
    slow: marks tests as slow running tests (includes rate limiting timing tests)
    unit: marks tests as unit tests
```

### Custom Markers

- `@pytest.mark.integration`: Tests that make real API calls
- `@pytest.mark.slow`: Tests that take significant time (>2 seconds, includes rate limiting timing tests)
- `@pytest.mark.unit`: Pure unit tests (default, no marker needed)

### Running Specific Tests

```bash
# Run specific test file
pytest tests/test_trafapy.py -v
pytest tests/test_rate_limiting.py -v

# Run specific test class
pytest tests/test_trafapy.py::TestTrafikanalysClient -v
pytest tests/test_rate_limiting.py::TestRateLimiter -v

# Run specific test method  
pytest tests/test_trafapy.py::TestAPICache::test_cache_initialization -v
pytest tests/test_rate_limiting.py::TestRateLimiter::test_wait_if_needed_rate_limiting -v

# Run tests matching a pattern
pytest -k "build_query" -v
pytest -k "rate_limit" -v

# Exclude specific tests
pytest -k "not cache_warming_strategy" -v
pytest -k "not slow" -v  # Skip slow timing tests
```

## 📊 Coverage Reports

Generate coverage reports to ensure comprehensive testing:

```bash
# Terminal coverage report
pytest -m "not integration" --cov=trafapy --cov-report=term-missing

# Generate HTML coverage report
pytest -m "not integration" --cov=trafapy --cov-report=html

# Using the test runner
python tests/run_tests.py --coverage-report
```

**Coverage targets:**
- **Overall coverage**: >90%
- **Core modules**: >95%
- **Critical paths**: 100%
- **Rate limiting module**: >95%

The HTML report (`htmlcov/index.html`) shows:
- Line-by-line coverage visualization
- Untested code paths
- Branch coverage information
- Missing test areas
- Rate limiting code coverage details

## 🔧 Test Runner Usage

The custom test runner (`tests/run_tests.py`) provides convenient commands:

```bash
# Basic usage
python tests/run_tests.py --unit              # Unit tests only
python tests/run_tests.py --integration       # Integration tests only
python tests/run_tests.py --all               # All tests
python tests/run_tests.py --fast              # Fast tests only

# With options
python tests/run_tests.py --unit --verbose    # Verbose output
python tests/run_tests.py --unit --coverage   # With coverage
python tests/run_tests.py --coverage-report   # Detailed HTML report

# Code quality checks
python tests/run_tests.py --lint              # Run flake8, black, mypy
```

## 🐛 Troubleshooting

### Common Issues and Solutions

#### Import Errors
```bash
# Solution: Install in development mode
pip install -e .

# Verify installation
python -c "import trafapy; print('Success!')"
```

#### Missing Dependencies
```bash
# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Or install all development dependencies
pip install -r requirements-test.txt
```

#### Cache Directory Issues
```bash
# Clean cache manually
rm -rf ~/.trafapy_cache

# Or in tests
shutil.rmtree(temp_dir, ignore_errors=True)
```

#### Integration Test Failures
- Check internet connectivity
- Verify Trafikanalys API is accessible
- Look for rate limiting (429 errors)
- Try running individual tests with `pytest -s` for debug output

#### Unknown Marker Warnings
```bash
# Make sure pytest.ini is properly configured
# Add markers to pytest.ini if needed
```

### Debug Mode

```bash
# Run with debug output
pytest -s -v --tb=long

# Enable client debug mode
client = TrafikanalysClient(debug=True)

# Show print statements
pytest -s tests/test_file.py::test_method
```

## 📈 Performance Considerations

- **Unit tests** should complete in <10 seconds total
- **Individual tests** should complete in <1 second
- Use **caching** to speed up repeated test runs
- **Mock expensive operations** like HTTP requests
- Avoid creating **large test datasets** in memory

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://docs.python.org/3/library/unittest.html)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [Trafikanalys API Documentation](https://www.trafa.se/sidor/oppen-data-api/)

## 🤝 Contributing Tests

When contributing to TrafaPy:

1. **Write tests first** (TDD approach recommended)
2. **Ensure >90% coverage** for new code
3. **Include both positive and negative test cases**
4. **Update this documentation** for new test patterns
5. **Run full test suite** before submitting PRs:

```bash
# Pre-contribution checklist
python tests/run_tests.py --all --lint --coverage
```

6. **Add appropriate markers** for new test types
7. **Use descriptive test and commit messages**

## Dependency Licenses

TrafaPy includes the following dependencies:

**Runtime Dependencies:**
- requests
- pandas

**Development/Testing Dependencies (not distributed):**
- pytest
- pytest-cov
- pytest-mock

All dependency licenses are available in the `LICENSES/` directory.

---

## 📞 Support

If you encounter testing issues:

1. **Check this documentation** for common solutions
2. **Run with verbose output**: `pytest -v -s`
3. **Check test isolation**: Run individual tests
4. **Verify dependencies**: `pip list | grep pytest`
5. **Clean environment**: Remove cache and temporary files

**Remember**: A passing test suite means your TrafaPy installation is working correctly! 🎉