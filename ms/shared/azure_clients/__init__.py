"""
Azure clients package

This package provides Azure service clients with managed identity authentication.
"""

from .auth import AzureClientBase, create_credential
from .openai_client import DirectOpenAIClient
from .search_client import DirectSearchClient
from .blob_client import DirectBlobClient
from .servicebus_client import DirectServiceBusClient
