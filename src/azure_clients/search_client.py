"""
Azure AI Search client for document indexing

This module provides a direct HTTP client for Azure AI Search API with managed identity
authentication and document upload capabilities.
"""

import logging
import requests
from typing import List, Dict, Any

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    SEARCH_API_VERSION, REQUEST_TIMEOUT_SECONDS, HTTP_SUCCESS_CODES,
    MAX_RETRIES, RETRY_DELAY_SECONDS, HTTP_AUTH_BEARER_PREFIX, VECTOR_DISPLAY_TEXT
)

logger = logging.getLogger(__name__)


class DirectSearchClient(AzureClientBase):
    """
    Direct HTTP client for Azure AI Search API
    
    This client uses managed identity authentication and provides methods
    for uploading documents to Azure AI Search indexes.
    """
    
    def __init__(self, endpoint: str, credential, scope: str, index_name: str, 
                 api_version: str = SEARCH_API_VERSION):
        """
        Initialize the Search client
        
        Args:
            endpoint: Azure AI Search endpoint URL
            credential: Azure credential instance
            scope: Token scope for authentication
            index_name: Name of the search index
            api_version: API version to use
        """
        super().__init__(credential, scope)
        self.endpoint = endpoint.rstrip('/')
        self.index_name = index_name
        self.api_version = api_version
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def upload_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Upload documents using direct HTTP call
        
        Args:
            documents: List of documents to upload
            
        Returns:
            bool: True if upload successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={self.api_version}"
        headers = await self._get_headers()
        
        payload = {
            "value": documents
        }
        
        # Log detailed information about the request
        logger.info(f"   START SEARCH Index Upload Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document count: {len(documents)}")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        # Log sample document structure (first document only)
        if documents:
            sample_doc = documents[0].copy()
            if 'vector' in sample_doc:
                vector_dim = len(sample_doc['vector']) if sample_doc['vector'] else 0
                sample_doc['vector'] = VECTOR_DISPLAY_TEXT.format(vector_dim)
            logger.info(f"   Document: {sample_doc['id']}")

        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   Search Response - Status: {response.status_code}")
        logger.info(f"   Response headers: {dict(response.headers)}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Search API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Search Upload successful - Response: {result}")
        logger.info(f"Successfully uploaded {len(documents)} documents to search index")
        return True
