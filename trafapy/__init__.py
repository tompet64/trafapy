"""
Trafikanalys API Python Wrapper

A Python package for interacting with the Trafikanalys API.
"""

__version__ = "1.0.0"

from .client import TrafikanalysClient, APIResponseError, BatchRequestError
from .cache_utils import APICache, DEFAULT_CACHE_DIR
