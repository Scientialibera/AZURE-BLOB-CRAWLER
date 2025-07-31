"""
Azure Blob Storage client for full CRUD operations

This module provides a direct client for Azure Blob Storage API with managed identity
authentication and comprehensive blob operations including Create, Read, Update, Delete.
"""

import logging
import requests
from typing import Tuple, Optional, List, Dict, Any, Union, IO
from io import BytesIO
import json

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_DELAY_SECONDS, 
    HTTP_AUTH_BEARER_PREFIX, AZURE_STORAGE_SCOPE, HTTP_SUCCESS_CODES
)

logger = logging.getLogger(__name__)


class DirectBlobClient(AzureClientBase):
    """
    Direct HTTP client for Azure Blob Storage API
    
    This client uses managed identity authentication and provides comprehensive CRUD methods
    for Azure Blob Storage including upload, download, update, delete, and listing operations.
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
        
    # ====== CREATE OPERATIONS ======
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def upload_blob(self, container_name: str, blob_name: str, 
                         data: Union[bytes, str, IO], 
                         content_type: Optional[str] = None,
                         metadata: Optional[Dict[str, str]] = None,
                         overwrite: bool = True) -> bool:
        """
        Upload blob content using direct HTTP call
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            data: Data to upload (bytes, string, or file-like object)
            content_type: Content type of the blob
            metadata: Metadata dictionary
            overwrite: Whether to overwrite existing blob
            
        Returns:
            bool: True if upload successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}/{blob_name}"
        headers = await self._get_headers()
        
        # Process data
        if isinstance(data, str):
            data = data.encode('utf-8')
            if not content_type:
                content_type = 'text/plain; charset=utf-8'
        elif hasattr(data, 'read'):
            data = data.read()
        
        if content_type:
            headers['Content-Type'] = content_type
        else:
            headers['Content-Type'] = 'application/octet-stream'
            
        headers['x-ms-blob-type'] = 'BlockBlob'
        
        # Add metadata headers
        if metadata:
            for key, value in metadata.items():
                headers[f'x-ms-meta-{key}'] = value
        
        # Add conditional headers
        if not overwrite:
            headers['If-None-Match'] = '*'
        
        logger.info(f"   START BLOB Upload Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Blob: {blob_name}")
        logger.info(f"   Data size: {len(data)} bytes")
        logger.info(f"   Content-Type: {content_type}")
        logger.info(f"   Overwrite: {overwrite}")
        
        response = requests.put(url, headers=headers, data=data, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Blob Upload Response - Status: {response.status_code}")
        
        if response.status_code not in [200, 201]:
            logger.error(f"   Blob Upload API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        logger.info(f"   Blob Upload successful - Uploaded {len(data)} bytes")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def create_container(self, container_name: str, 
                              metadata: Optional[Dict[str, str]] = None,
                              public_access: Optional[str] = None) -> bool:
        """
        Create a container
        
        Args:
            container_name: Name of the container to create
            metadata: Metadata dictionary
            public_access: Public access level ('blob', 'container', or None)
            
        Returns:
            bool: True if creation successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}?restype=container"
        headers = await self._get_headers()
        
        # Add metadata headers
        if metadata:
            for key, value in metadata.items():
                headers[f'x-ms-meta-{key}'] = value
        
        # Set public access level
        if public_access:
            headers['x-ms-blob-public-access'] = public_access
        
        logger.info(f"   START BLOB Create Container Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Public access: {public_access}")
        
        response = requests.put(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Create Container Response - Status: {response.status_code}")
        
        if response.status_code == 409:
            logger.info(f"   Container {container_name} already exists")
            return True
        elif response.status_code not in [200, 201]:
            logger.error(f"   Create Container API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
            response.raise_for_status()
        
        logger.info(f"   Container {container_name} created successfully")
        return True
        
    # ====== READ OPERATIONS ======
        
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
            'blob_type': response.headers.get('x-ms-blob-type', ''),
            'lease_status': response.headers.get('x-ms-lease-status', ''),
            'lease_state': response.headers.get('x-ms-lease-state', ''),
        }
        
        # Extract metadata
        metadata = {}
        for key, value in response.headers.items():
            if key.lower().startswith('x-ms-meta-'):
                metadata_key = key[10:]  # Remove 'x-ms-meta-' prefix
                metadata[metadata_key] = value
        properties['metadata'] = metadata
        
        logger.info(f"   Blob Properties successful - Size: {properties['size']} bytes")
        return properties
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def download_blob(self, container_name: str, blob_name: str, 
                           range_start: Optional[int] = None,
                           range_end: Optional[int] = None) -> bytes:
        """
        Download blob content using direct HTTP call
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            range_start: Start byte position for partial download
            range_end: End byte position for partial download
            
        Returns:
            bytes: Blob content
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}/{blob_name}"
        headers = await self._get_headers()
        
        # Add range header if specified
        if range_start is not None or range_end is not None:
            range_start = range_start or 0
            range_str = f"bytes={range_start}-"
            if range_end is not None:
                range_str += str(range_end)
            headers['Range'] = range_str
        
        # Log detailed information about the request
        logger.info(f"   START BLOB Download Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Blob: {blob_name}")
        logger.info(f"   Range: {headers.get('Range', 'Full download')}")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   Blob Download Response - Status: {response.status_code}")
        logger.info(f"   Content-Length: {response.headers.get('Content-Length', 'Unknown')}")
        logger.info(f"   Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
        
        if response.status_code not in [200, 206]:  # 206 for partial content
            logger.error(f"   Blob Download API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        content = response.content
        logger.info(f"   Blob Download successful - Downloaded {len(content)} bytes")
        return content
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def list_blobs(self, container_name: str, prefix: Optional[str] = None,
                        max_results: Optional[int] = None,
                        include_metadata: bool = False) -> List[Dict[str, Any]]:
        """
        List blobs in a container
        
        Args:
            container_name: Name of the container
            prefix: Blob name prefix filter
            max_results: Maximum number of results
            include_metadata: Whether to include blob metadata
            
        Returns:
            List[Dict[str, Any]]: List of blob information
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}?restype=container&comp=list"
        
        params = []
        if prefix:
            params.append(f"prefix={prefix}")
        if max_results:
            params.append(f"maxresults={max_results}")
        if include_metadata:
            params.append("include=metadata")
            
        if params:
            url += "&" + "&".join(params)
        
        headers = await self._get_headers()
        
        logger.info(f"   START BLOB List Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Prefix: {prefix}")
        logger.info(f"   Max results: {max_results}")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   List Blobs Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   List Blobs API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        # Parse XML response (simplified - in production, use xml.etree.ElementTree)
        content = response.text
        blobs = []
        
        # Extract blob names and properties from XML (basic implementation)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(content)
        
        for blob_elem in root.findall('.//{https://schemas.microsoft.com/netservices/2010/10/servicebus/connect}Blob'):
            blob_info = {}
            name_elem = blob_elem.find('{https://schemas.microsoft.com/netservices/2010/10/servicebus/connect}Name')
            if name_elem is not None:
                blob_info['name'] = name_elem.text
                
            properties_elem = blob_elem.find('{https://schemas.microsoft.com/netservices/2010/10/servicebus/connect}Properties')
            if properties_elem is not None:
                for prop in properties_elem:
                    prop_name = prop.tag.split('}')[-1] if '}' in prop.tag else prop.tag
                    blob_info[prop_name.lower()] = prop.text
                    
            blobs.append(blob_info)
        
        logger.info(f"   List Blobs successful - Found {len(blobs)} blobs")
        return blobs
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def list_containers(self, prefix: Optional[str] = None,
                             max_results: Optional[int] = None,
                             include_metadata: bool = False) -> List[Dict[str, Any]]:
        """
        List containers in the storage account
        
        Args:
            prefix: Container name prefix filter
            max_results: Maximum number of results
            include_metadata: Whether to include container metadata
            
        Returns:
            List[Dict[str, Any]]: List of container information
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/?comp=list"
        
        params = []
        if prefix:
            params.append(f"prefix={prefix}")
        if max_results:
            params.append(f"maxresults={max_results}")
        if include_metadata:
            params.append("include=metadata")
            
        if params:
            url += "&" + "&".join(params)
        
        headers = await self._get_headers()
        
        logger.info(f"   START BLOB List Containers Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Prefix: {prefix}")
        logger.info(f"   Max results: {max_results}")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   List Containers Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   List Containers API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        # Parse XML response (simplified)
        content = response.text
        containers = []
        
        import xml.etree.ElementTree as ET
        root = ET.fromstring(content)
        
        for container_elem in root.findall('.//{https://schemas.microsoft.com/netservices/2010/10/servicebus/connect}Container'):
            container_info = {}
            name_elem = container_elem.find('{https://schemas.microsoft.com/netservices/2010/10/servicebus/connect}Name')
            if name_elem is not None:
                container_info['name'] = name_elem.text
                
            properties_elem = container_elem.find('{https://schemas.microsoft.com/netservices/2010/10/servicebus/connect}Properties')
            if properties_elem is not None:
                for prop in properties_elem:
                    prop_name = prop.tag.split('}')[-1] if '}' in prop.tag else prop.tag
                    container_info[prop_name.lower()] = prop.text
                    
            containers.append(container_info)
        
        logger.info(f"   List Containers successful - Found {len(containers)} containers")
        return containers
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def blob_exists(self, container_name: str, blob_name: str) -> bool:
        """
        Check if a blob exists
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            
        Returns:
            bool: True if blob exists, False otherwise
        """
        try:
            await self.get_blob_properties(container_name, blob_name)
            return True
        except Exception as e:
            if hasattr(e, 'response') and e.response and e.response.status_code == 404:
                return False
            raise
    
    # ====== UPDATE OPERATIONS ======
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def set_blob_metadata(self, container_name: str, blob_name: str,
                               metadata: Dict[str, str]) -> bool:
        """
        Set blob metadata
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            metadata: Metadata dictionary
            
        Returns:
            bool: True if metadata set successfully, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}/{blob_name}?comp=metadata"
        headers = await self._get_headers()
        
        # Add metadata headers
        for key, value in metadata.items():
            headers[f'x-ms-meta-{key}'] = value
        
        logger.info(f"   START BLOB Set Metadata Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Blob: {blob_name}")
        logger.info(f"   Metadata keys: {list(metadata.keys())}")
        
        response = requests.put(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Set Blob Metadata Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Set Blob Metadata API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        logger.info(f"   Set Blob Metadata successful")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def copy_blob(self, source_container: str, source_blob: str,
                       dest_container: str, dest_blob: str,
                       metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Copy a blob to another location
        
        Args:
            source_container: Source container name
            source_blob: Source blob name
            dest_container: Destination container name
            dest_blob: Destination blob name
            metadata: Optional metadata for the destination blob
            
        Returns:
            bool: True if copy successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        dest_url = f"{self.account_url}/{dest_container}/{dest_blob}"
        source_url = f"{self.account_url}/{source_container}/{source_blob}"
        
        headers = await self._get_headers()
        headers['x-ms-copy-source'] = source_url
        
        # Add metadata headers if provided
        if metadata:
            for key, value in metadata.items():
                headers[f'x-ms-meta-{key}'] = value
        
        logger.info(f"   START BLOB Copy Request:")
        logger.info(f"   Source: {source_container}/{source_blob}")
        logger.info(f"   Destination: {dest_container}/{dest_blob}")
        
        response = requests.put(dest_url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Copy Blob Response - Status: {response.status_code}")
        
        if response.status_code not in [200, 202]:
            logger.error(f"   Copy Blob API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        logger.info(f"   Copy Blob successful")
        return True
    
    # ====== DELETE OPERATIONS ======
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def delete_blob(self, container_name: str, blob_name: str,
                         delete_snapshots: Optional[str] = None) -> bool:
        """
        Delete a blob
        
        Args:
            container_name: Name of the container
            blob_name: Name of the blob
            delete_snapshots: How to handle snapshots ('include', 'only', or None)
            
        Returns:
            bool: True if deletion successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.account_url}/{container_name}/{blob_name}"
        headers = await self._get_headers()
        
        if delete_snapshots:
            headers['x-ms-delete-snapshots'] = delete_snapshots
        
        logger.info(f"   START BLOB Delete Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Container: {container_name}")
        logger.info(f"   Blob: {blob_name}")
        logger.info(f"   Delete snapshots: {delete_snapshots}")
        
        response = requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Delete Blob Response - Status: {response.status_code}")
        
        if response.status_code == 404:
            logger.info(f"   Blob {blob_name} not found (already deleted)")
            return True
        elif response.status_code not in [200, 202]:
            logger.error(f"   Delete Blob API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
            response.raise_for_status()
        
        logger.info(f"   Delete Blob successful")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def delete_blobs(self, container_name: str, blob_names: List[str],
                          delete_snapshots: Optional[str] = None) -> Dict[str, bool]:
        """
        Delete multiple blobs
        
        Args:
            container_name: Name of the container
            blob_names: List of blob names to delete
            delete_snapshots: How to handle snapshots ('include', 'only', or None)
            
        Returns:
            Dict[str, bool]: Dictionary mapping blob names to deletion success
        """
        results = {}
        for blob_name in blob_names:
            try:
                success = await self.delete_blob(container_name, blob_name, delete_snapshots)
                results[blob_name] = success
            except Exception as e:
                logger.error(f"   Failed to delete blob {blob_name}: {e}")
                results[blob_name] = False
        
        successful_deletes = sum(1 for success in results.values() if success)
        logger.info(f"   Bulk delete completed: {successful_deletes}/{len(blob_names)} successful")
        return results
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def delete_container(self, container_name: str, confirm: bool = False) -> bool:
        """
        Delete a container (DANGEROUS OPERATION)
        
        Args:
            container_name: Name of the container to delete
            confirm: Must be True to confirm the operation
            
        Returns:
            bool: True if deletion successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
            ValueError: If confirm is not True
        """
        if not confirm:
            raise ValueError("Must set confirm=True to delete a container")
        
        url = f"{self.account_url}/{container_name}?restype=container"
        headers = await self._get_headers()
        
        logger.warning(f"   START BLOB Delete Container Request:")
        logger.warning(f"   URL: {url}")
        logger.warning(f"   Container: {container_name}")
        logger.warning(f"   This will delete the container and all its contents!")
        
        response = requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Delete Container Response - Status: {response.status_code}")
        
        if response.status_code == 404:
            logger.info(f"   Container {container_name} not found (already deleted)")
            return True
        elif response.status_code not in [200, 202]:
            logger.error(f"   Delete Container API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
            response.raise_for_status()
        
        logger.warning(f"   Container {container_name} deleted successfully")
        return True
        
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
    our DirectBlobClient internally for consistent authentication and enhanced functionality.
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
        
    async def download_blob(self, range_start: Optional[int] = None, range_end: Optional[int] = None):
        """
        Download blob (compatibility method)
        
        Args:
            range_start: Start byte position for partial download
            range_end: End byte position for partial download
        
        Returns:
            BlobDownloadWrapper: Wrapper with readall method
        """
        content = await self.blob_client.download_blob(self.container_name, self.blob_name, range_start, range_end)
        return BlobDownloadWrapper(content)
    
    async def upload_blob(self, data: Union[bytes, str, IO], 
                         content_type: Optional[str] = None,
                         metadata: Optional[Dict[str, str]] = None,
                         overwrite: bool = True):
        """
        Upload blob (compatibility method)
        
        Args:
            data: Data to upload
            content_type: Content type of the blob
            metadata: Metadata dictionary
            overwrite: Whether to overwrite existing blob
            
        Returns:
            bool: True if upload successful
        """
        return await self.blob_client.upload_blob(
            self.container_name, self.blob_name, data, content_type, metadata, overwrite
        )
    
    async def delete_blob(self, delete_snapshots: Optional[str] = None):
        """
        Delete blob (compatibility method)
        
        Args:
            delete_snapshots: How to handle snapshots
            
        Returns:
            bool: True if deletion successful
        """
        return await self.blob_client.delete_blob(self.container_name, self.blob_name, delete_snapshots)
    
    async def set_blob_metadata(self, metadata: Dict[str, str]):
        """
        Set blob metadata (compatibility method)
        
        Args:
            metadata: Metadata dictionary
            
        Returns:
            bool: True if metadata set successfully
        """
        return await self.blob_client.set_blob_metadata(self.container_name, self.blob_name, metadata)
    
    async def exists(self):
        """
        Check if blob exists (compatibility method)
        
        Returns:
            bool: True if blob exists
        """
        return await self.blob_client.blob_exists(self.container_name, self.blob_name)


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
        self.blob_type = properties.get('blob_type', '')
        self.lease_status = properties.get('lease_status', '')
        self.lease_state = properties.get('lease_state', '')
        self.metadata = properties.get('metadata', {})


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
