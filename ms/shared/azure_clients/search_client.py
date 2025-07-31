"""
Azure AI Search client for full CRUD operations

This module provides a direct HTTP client for Azure AI Search API with managed identity
authentication and comprehensive document operations including Create, Read, Update, Delete.
"""

import logging
import requests
from typing import List, Dict, Any, Optional, Union

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    SEARCH_API_VERSION, REQUEST_TIMEOUT_SECONDS, HTTP_SUCCESS_CODES,
    MAX_RETRIES, RETRY_DELAY_SECONDS, HTTP_AUTH_BEARER_PREFIX, VECTOR_DISPLAY_TEXT,
    SEARCH_ACTION_UPLOAD, DOCUMENT_ID_FIELD
)

logger = logging.getLogger(__name__)


class DirectSearchClient(AzureClientBase):
    """
    Direct HTTP client for Azure AI Search API
    
    This client uses managed identity authentication and provides comprehensive CRUD methods
    for Azure AI Search indexes including document upload, search, update, and deletion.
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
        
    # ====== CREATE OPERATIONS ======
        
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
        
        # Ensure all documents have the upload action
        processed_documents = []
        for doc in documents:
            doc_copy = doc.copy()
            doc_copy['@search.action'] = SEARCH_ACTION_UPLOAD
            processed_documents.append(doc_copy)
        
        payload = {
            "value": processed_documents
        }
        
        # Log detailed information about the request
        logger.info(f"   START SEARCH Index Upload Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document count: {len(processed_documents)}")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        # Log sample document structure (first document only)
        if processed_documents:
            sample_doc = processed_documents[0].copy()
            if 'vector' in sample_doc:
                vector_dim = len(sample_doc['vector']) if sample_doc['vector'] else 0
                sample_doc['vector'] = VECTOR_DISPLAY_TEXT.format(vector_dim)
            logger.info(f"   Document: {sample_doc.get('id', 'Unknown ID')}")

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
        logger.info(f"Successfully uploaded {len(processed_documents)} documents to search index")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def create_document(self, document: Dict[str, Any]) -> bool:
        """
        Create a single document in the search index
        
        Args:
            document: Document to create
            
        Returns:
            bool: True if creation successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        return await self.upload_documents([document])
    
    # ====== READ OPERATIONS ======
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def search_documents(self, query: str, filters: Optional[str] = None, 
                             top: int = 50, skip: int = 0, 
                             select: Optional[List[str]] = None,
                             order_by: Optional[List[str]] = None,
                             include_total_count: bool = False,
                             search_mode: str = "any",
                             query_type: str = "simple") -> Dict[str, Any]:
        """
        Search documents in the index
        
        Args:
            query: Search query string
            filters: OData filter expression
            top: Number of results to return
            skip: Number of results to skip
            select: Fields to return
            order_by: Fields to order by
            include_total_count: Whether to include total count
            search_mode: Search mode (any, all)
            query_type: Query type (simple, full, semantic)
            
        Returns:
            Dict[str, Any]: Search results
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/search?api-version={self.api_version}"
        headers = await self._get_headers()
        
        payload = {
            "search": query,
            "top": top,
            "skip": skip,
            "count": include_total_count,
            "searchMode": search_mode,
            "queryType": query_type
        }
        
        if filters:
            payload["filter"] = filters
        if select:
            payload["select"] = ",".join(select)
        if order_by:
            payload["orderby"] = ",".join(order_by)
        
        logger.info(f"   START SEARCH Query Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Query: {query}")
        logger.info(f"   Filter: {filters}")
        logger.info(f"   Top: {top}, Skip: {skip}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Search Query Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Search Query API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        result_count = len(result.get("value", []))
        total_count = result.get("@odata.count", "unknown")
        logger.info(f"   Search Query successful - Returned {result_count} results (total: {total_count})")
        return result
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def get_document(self, document_id: str, select: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific document by ID
        
        Args:
            document_id: ID of the document to retrieve
            select: Fields to return
            
        Returns:
            Optional[Dict[str, Any]]: Document data or None if not found
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs('{document_id}')?api-version={self.api_version}"
        if select:
            url += f"&$select={','.join(select)}"
            
        headers = await self._get_headers()
        
        logger.info(f"   START SEARCH Get Document Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document ID: {document_id}")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Get Document Response - Status: {response.status_code}")
        
        if response.status_code == 404:
            logger.info(f"   Document {document_id} not found")
            return None
        elif response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Get Document API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
            response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Get Document successful - Retrieved document {document_id}")
        return result
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def count_documents(self, filters: Optional[str] = None) -> int:
        """
        Count documents in the index
        
        Args:
            filters: OData filter expression
            
        Returns:
            int: Number of documents
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/$count?api-version={self.api_version}"
        if filters:
            url += f"&$filter={filters}"
            
        headers = await self._get_headers()
        
        logger.info(f"   START SEARCH Count Documents Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Filter: {filters}")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Count Documents Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Count Documents API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        count = int(response.text)
        logger.info(f"   Count Documents successful - Total: {count}")
        return count
    
    # ====== UPDATE OPERATIONS ======
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def update_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Update existing documents (merge operation)
        
        Args:
            documents: List of documents to update
            
        Returns:
            bool: True if update successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={self.api_version}"
        headers = await self._get_headers()
        
        # Set action to merge for updates
        processed_documents = []
        for doc in documents:
            doc_copy = doc.copy()
            doc_copy['@search.action'] = 'merge'
            processed_documents.append(doc_copy)
        
        payload = {
            "value": processed_documents
        }
        
        logger.info(f"   START SEARCH Update Documents Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document count: {len(processed_documents)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Update Documents Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Update Documents API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Update Documents successful - Response: {result}")
        logger.info(f"Successfully updated {len(processed_documents)} documents in search index")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def update_document(self, document: Dict[str, Any]) -> bool:
        """
        Update a single document (merge operation)
        
        Args:
            document: Document to update
            
        Returns:
            bool: True if update successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        return await self.update_documents([document])
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def upsert_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Upsert documents (upload or merge if exists)
        
        Args:
            documents: List of documents to upsert
            
        Returns:
            bool: True if upsert successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={self.api_version}"
        headers = await self._get_headers()
        
        # Set action to uploadOrMerge for upserts
        processed_documents = []
        for doc in documents:
            doc_copy = doc.copy()
            doc_copy['@search.action'] = 'uploadOrMerge'
            processed_documents.append(doc_copy)
        
        payload = {
            "value": processed_documents
        }
        
        logger.info(f"   START SEARCH Upsert Documents Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document count: {len(processed_documents)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Upsert Documents Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Upsert Documents API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Upsert Documents successful - Response: {result}")
        logger.info(f"Successfully upserted {len(processed_documents)} documents in search index")
        return True
    
    # ====== DELETE OPERATIONS ======
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def delete_documents(self, document_ids: Union[List[str], List[Dict[str, Any]]]) -> bool:
        """
        Delete documents by ID or document objects
        
        Args:
            document_ids: List of document IDs (strings) or document objects with ID field
            
        Returns:
            bool: True if deletion successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={self.api_version}"
        headers = await self._get_headers()
        
        # Process documents for deletion
        processed_documents = []
        for item in document_ids:
            if isinstance(item, str):
                # String ID provided
                doc = {DOCUMENT_ID_FIELD: item, '@search.action': 'delete'}
            elif isinstance(item, dict):
                # Document object provided
                doc = {DOCUMENT_ID_FIELD: item.get(DOCUMENT_ID_FIELD), '@search.action': 'delete'}
                if not doc[DOCUMENT_ID_FIELD]:
                    raise ValueError(f"Document object must contain '{DOCUMENT_ID_FIELD}' field")
            else:
                raise ValueError("document_ids must contain strings or dictionary objects")
            processed_documents.append(doc)
        
        payload = {
            "value": processed_documents
        }
        
        logger.info(f"   START SEARCH Delete Documents Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document count: {len(processed_documents)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Delete Documents Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Delete Documents API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Delete Documents successful - Response: {result}")
        logger.info(f"Successfully deleted {len(processed_documents)} documents from search index")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def delete_document(self, document_id: str) -> bool:
        """
        Delete a single document by ID
        
        Args:
            document_id: ID of the document to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        return await self.delete_documents([document_id])
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def clear_index(self, confirm: bool = False) -> bool:
        """
        Delete all documents from the index (DANGEROUS OPERATION)
        
        Args:
            confirm: Must be True to confirm the operation
            
        Returns:
            bool: True if clearing successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
            ValueError: If confirm is not True
        """
        if not confirm:
            raise ValueError("Must set confirm=True to clear the entire index")
        
        # First, get all document IDs
        search_result = await self.search_documents(
            query="*", 
            select=[DOCUMENT_ID_FIELD], 
            top=1000,  # Adjust based on your index size
            include_total_count=True
        )
        
        document_ids = [doc[DOCUMENT_ID_FIELD] for doc in search_result.get("value", [])]
        total_count = search_result.get("@odata.count", len(document_ids))
        
        logger.warning(f"   Clearing index {self.index_name} - {total_count} documents will be deleted")
        
        if not document_ids:
            logger.info(f"   Index {self.index_name} is already empty")
            return True
        
        # Delete documents in batches if necessary
        batch_size = 1000  # Azure Search batch limit
        for i in range(0, len(document_ids), batch_size):
            batch = document_ids[i:i + batch_size]
            await self.delete_documents(batch)
            logger.info(f"   Deleted batch {i//batch_size + 1} ({len(batch)} documents)")
        
        logger.warning(f"   Index {self.index_name} cleared successfully")
        return True
    
    # ====== UTILITY METHODS ======
    
    async def get_index_statistics(self) -> Dict[str, Any]:
        """
        Get index statistics including document count and storage size
        
        Returns:
            Dict[str, Any]: Index statistics
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/stats?api-version={self.api_version}"
        headers = await self._get_headers()
        
        logger.info(f"   START SEARCH Index Statistics Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Index Statistics Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Index Statistics API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Index Statistics successful - Document count: {result.get('documentCount', 'unknown')}")
        return result
