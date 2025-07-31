"""
Azure Blob Storage client for file operations

This module provides a direct client for Azure Blob Storage API with managed identity
authentication and file download capabilities.
"""

import logging
import requests
from typing import Tuple, Optional

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_DELAY_SECONDS, 
    HTTP_AUTH_BEARER_PREFIX, AZURE_STORAGE_SCOPE
)

logger = logging.getLogger(__name__)


class DirectBlobClient(AzureClientBase):
    """
    Direct HTTP client for Azure Blob Storage API
    
    This client uses managed identity authentication and provides methods
    for accessing and downloading blobs from Azure Storage.
    """
    
    def __init__(self, account_url: str, credential):
        """
        Initialize the Blob client
        
        Args:
            account_url: Azure Storage account URL
            credential: Azure credential instance
        """
        super().__init__(credential, AZURE_STORAGE_SCOPE)
        self.account_url = account_url.rstrip('/')
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def get_blob_properties(self, container_name: str, blob_name: str) -> dict:
        """
        Get blob properties using direct HTTP call
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            
        Returns:
            dict: Blob properties including size, content type, etc.
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}/{blob_name}"
        headers = await self._get_headers()
        
        # Log detailed information about the request
        logger.info(f"   START BLOB Properties Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Blob: {blob_name}")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        response = requests.head(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   Blob Properties Response - Status: {response.status_code}")
        logger.info(f"   Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.error(f"   Blob Properties API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        # Extract properties from headers
        properties = {
            'size': int(response.headers.get('Content-Length', 0)),
            'content_type': response.headers.get('Content-Type', ''),
            'last_modified': response.headers.get('Last-Modified', ''),
            'etag': response.headers.get('ETag', ''),
            'content_encoding': response.headers.get('Content-Encoding', ''),
        }
        
        logger.info(f"   Blob Properties successful - Size: {properties['size']} bytes")
        return properties
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def download_blob(self, container_name: str, blob_name: str) -> bytes:
        """
        Download blob content using direct HTTP call
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            
        Returns:
            bytes: Blob content
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}/{blob_name}"
        headers = await self._get_headers()
        
        # Log detailed information about the request
        logger.info(f"   START BLOB Download Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Blob: {blob_name}")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   Blob Download Response - Status: {response.status_code}")
        logger.info(f"   Content-Length: {response.headers.get('Content-Length', 'Unknown')}")
        logger.info(f"   Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
        
        if response.status_code != 200:
            logger.error(f"   Blob Download API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        content = response.content
        logger.info(f"   Blob Download successful - Downloaded {len(content)} bytes")
        return content
        
    def get_blob_client(self, container: str, blob: str) -> 'BlobClientWrapper':
        """
        Get a blob client wrapper for compatibility with existing code
        
        Args:
            container: Container name
            blob: Blob name
            
        Returns:
            BlobClientWrapper: Wrapper that provides compatibility with azure.storage.blob.aio
        """
        return BlobClientWrapper(self, container, blob)


class BlobClientWrapper:
    """
    Wrapper class to provide compatibility with azure.storage.blob.aio.BlobClient
    
    This class provides the same interface as the Azure SDK blob client but uses
    our DirectBlobClient internally for consistent authentication.
    """
    
    def __init__(self, blob_client: DirectBlobClient, container_name: str, blob_name: str):
        """
        Initialize the blob client wrapper
        
        Args:
            blob_client: DirectBlobClient instance
            container_name: Name of the container
            blob_name: Name of the blob
        """
        self.blob_client = blob_client
        self.container_name = container_name
        self.blob_name = blob_name
        
    async def get_blob_properties(self):
        """
        Get blob properties (compatibility method)
        
        Returns:
            BlobPropertiesWrapper: Wrapper with size property
        """
        properties = await self.blob_client.get_blob_properties(self.container_name, self.blob_name)
        return BlobPropertiesWrapper(properties)
        
    async def download_blob(self):
        """
        Download blob (compatibility method)
        
        Returns:
            BlobDownloadWrapper: Wrapper with readall method
        """
        content = await self.blob_client.download_blob(self.container_name, self.blob_name)
        return BlobDownloadWrapper(content)


class BlobPropertiesWrapper:
    """Wrapper for blob properties to provide compatibility with Azure SDK"""
    
    def __init__(self, properties: dict):
        """
        Initialize properties wrapper
        
        Args:
            properties: Properties dictionary from DirectBlobClient
        """
        self.size = properties['size']
        self.content_type = properties['content_type']
        self.last_modified = properties['last_modified']
        self.etag = properties['etag']
        self.content_encoding = properties['content_encoding']


class BlobDownloadWrapper:
    """Wrapper for blob download to provide compatibility with Azure SDK"""
    
    def __init__(self, content: bytes):
        """
        Initialize download wrapper
        
        Args:
            content: Downloaded blob content
        """
        self.content = content
        
    async def readall(self) -> bytes:
        """
        Read all content (compatibility method)
        
        Returns:
            bytes: Blob content
        """
        return self.content
