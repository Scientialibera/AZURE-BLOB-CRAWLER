"""
Azure OpenAI client for embeddings generation

This module provides a direct HTTP client for Azure OpenAI API with managed identity
authentication and automatic retry logic.
"""

import logging
import requests
from typing import List

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    OPENAI_API_VERSION, OPENAI_EMBEDDING_MODEL, REQUEST_TIMEOUT_SECONDS,
    MAX_RETRIES, RETRY_DELAY_SECONDS, HTTP_AUTH_BEARER_PREFIX
)

logger = logging.getLogger(__name__)


class DirectOpenAIClient(AzureClientBase):
    """
    Direct HTTP client for Azure OpenAI API
    
    This client uses managed identity authentication and provides methods
    for generating embeddings using Azure OpenAI services.
    """
    
    def __init__(self, endpoint: str, credential, scope: str, api_version: str = OPENAI_API_VERSION):
        """
        Initialize the OpenAI client
        
        Args:
            endpoint: Azure OpenAI endpoint URL
            credential: Azure credential instance
            scope: Token scope for authentication
            api_version: API version to use
        """
        super().__init__(credential, scope)
        self.endpoint = endpoint.rstrip('/')
        self.api_version = api_version
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def create_embeddings(self, text: str, model: str = OPENAI_EMBEDDING_MODEL) -> List[float]:
        """
        Create embeddings using direct HTTP call
        
        Args:
            text: Text to generate embeddings for
            model: Model name to use for embeddings
            
        Returns:
            List[float]: Vector embeddings
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/openai/deployments/{model}/embeddings?api-version={self.api_version}"
        headers = await self._get_headers()
        
        payload = {
            "input": text,
            "model": model
        }
        
        # Log detailed information about the request
        logger.info(f"   START OPENAI Embeddings Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Model: {model}")
        logger.info(f"   Text length: {len(text)} chars")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   OpenAI Response - Status: {response.status_code}")
        logger.info(f"   Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.error(f"   OpenAI API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        embedding = result['data'][0]['embedding']
        logger.info(f"   OpenAI Embeddings successful - Vector dimension: {len(embedding)}")
        return embedding
