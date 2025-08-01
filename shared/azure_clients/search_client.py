"""
Azure AI Search client for document indexing

This module provides a direct HTTP client for Azure AI Search API with managed identity
authentication and document upload capabilities.
"""

import logging
import requests
from typing import List, Dict, Any, Optional, Union
from enum import Enum

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    SEARCH_API_VERSION, REQUEST_TIMEOUT_SECONDS, HTTP_SUCCESS_CODES,
    MAX_RETRIES, RETRY_DELAY_SECONDS, HTTP_AUTH_BEARER_PREFIX, VECTOR_DISPLAY_TEXT,
    DOCUMENT_ID_FIELD, DOCUMENT_CONTENT_FIELD, DOCUMENT_VECTOR_FIELD, SEARCH_ACTION_FIELD,
    SEARCH_ACTION_DELETE
)

logger = logging.getLogger(__name__)


class SearchType(Enum):
    """Search type enumeration for different search modes"""
    HYBRID = "hybrid"
    VECTOR_ONLY = "vector"
    TEXT_ONLY = "text"


class SearchResult:
    """Class to represent search results"""
    def __init__(self, documents: List[Dict[str, Any]], count: int = None):
        self.documents = documents
        self.count = count or len(documents)
    
    def __iter__(self):
        return iter(self.documents)
    
    def __len__(self):
        return self.count


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
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def delete_document(self, document_id: str) -> bool:
        """
        Delete a document by ID
        
        Args:
            document_id: ID of the document to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
            
        Raises:
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={self.api_version}"
        headers = await self._get_headers()
        
        payload = {
            "value": [{
                SEARCH_ACTION_FIELD: SEARCH_ACTION_DELETE,
                DOCUMENT_ID_FIELD: document_id
            }]
        }
        
        logger.info(f"   START SEARCH Delete Document Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document ID: {document_id}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Delete Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Search Delete API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Search Delete successful - Response: {result}")
        logger.info(f"Successfully deleted document {document_id} from search index")
        return True
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def update_document(self, document: Dict[str, Any]) -> bool:
        """
        Update a document by first deleting it (by ID) and then uploading the new version
        
        Args:
            document: Document to update (must contain 'id' field)
            
        Returns:
            bool: True if update successful, False otherwise
            
        Raises:
            ValueError: If document doesn't contain required 'id' field
            Exception: If API call fails after all retries
        """
        if DOCUMENT_ID_FIELD not in document:
            raise ValueError(f"Document must contain '{DOCUMENT_ID_FIELD}' field for update operation")
        
        document_id = document[DOCUMENT_ID_FIELD]
        logger.info(f"Starting update operation for document: {document_id}")
        
        # First delete the existing document
        try:
            await self.delete_document(document_id)
            logger.info(f"Successfully deleted existing document: {document_id}")
        except Exception as e:
            # If delete fails because document doesn't exist, that's ok, continue with upload
            logger.warning(f"Delete operation failed for document {document_id} (document may not exist): {e}")
        
        # Then upload the new version
        return await self.upload_documents([document])
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def search(self, 
                    search_text: Optional[str] = None,
                    vector: Optional[List[float]] = None,
                    search_type: SearchType = SearchType.HYBRID,
                    top: int = 10,
                    select: Optional[List[str]] = None,
                    filter_query: Optional[str] = None,
                    vector_filter_mode: str = "preFilter") -> SearchResult:
        """
        Perform search operations (hybrid, vector-only, or text-only)
        
        Args:
            search_text: Text query for search
            vector: Vector for similarity search
            search_type: Type of search to perform (hybrid, vector, or text)
            top: Number of results to return
            select: Fields to include in results
            filter_query: OData filter expression
            vector_filter_mode: Vector filter mode ("preFilter" or "postFilter")
            
        Returns:
            SearchResult: Search results with documents and count
            
        Raises:
            ValueError: If required parameters are missing for the search type
            Exception: If API call fails after all retries
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/search?api-version={self.api_version}"
        headers = await self._get_headers()
        
        # Validate inputs based on search type
        if search_type == SearchType.TEXT_ONLY and not search_text:
            raise ValueError("search_text is required for text-only search")
        elif search_type == SearchType.VECTOR_ONLY and not vector:
            raise ValueError("vector is required for vector-only search")
        elif search_type == SearchType.HYBRID and not (search_text or vector):
            raise ValueError("Either search_text or vector (or both) is required for hybrid search")
        
        # Build the search payload
        payload = {
            "top": top,
            "count": True
        }
        
        # Add search text if provided and search type allows it
        if search_text and search_type != SearchType.VECTOR_ONLY:
            payload["search"] = search_text
        
        # Add vector search if provided and search type allows it
        if vector and search_type != SearchType.TEXT_ONLY:
            payload["vectorQueries"] = [{
                "vector": vector,
                "fields": DOCUMENT_VECTOR_FIELD,
                "k": top
            }]
            
            # Add vector filter if specified
            if filter_query:
                payload["vectorQueries"][0]["filter"] = filter_query
                payload["vectorFilterMode"] = vector_filter_mode
        
        # Add traditional filter if specified and not using vector-only search
        if filter_query and search_type != SearchType.VECTOR_ONLY:
            payload["filter"] = filter_query
        
        # Add field selection if specified
        if select:
            payload["select"] = ",".join(select)
        
        # Log search details
        logger.info(f"   START SEARCH Query Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Search Type: {search_type.value}")
        logger.info(f"   Search Text: {search_text}")
        logger.info(f"   Vector Dimensions: {len(vector) if vector else 0}")
        logger.info(f"   Top Results: {top}")
        logger.info(f"   Filter: {filter_query}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.info(f"   Search Query Response - Status: {response.status_code}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Search Query API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        documents = result.get("value", [])
        count = result.get("@odata.count", len(documents))
        
        logger.info(f"   Search Query successful - Found {count} documents")
        logger.info(f"   Returned {len(documents)} documents")
        
        return SearchResult(documents, count)
    
    async def search_hybrid(self, 
                           search_text: str,
                           vector: List[float],
                           top: int = 10,
                           select: Optional[List[str]] = None,
                           filter_query: Optional[str] = None) -> SearchResult:
        """
        Convenience method for hybrid search
        
        Args:
            search_text: Text query for search
            vector: Vector for similarity search
            top: Number of results to return
            select: Fields to include in results
            filter_query: OData filter expression
            
        Returns:
            SearchResult: Search results with documents and count
        """
        return await self.search(
            search_text=search_text,
            vector=vector,
            search_type=SearchType.HYBRID,
            top=top,
            select=select,
            filter_query=filter_query
        )
    
    async def search_vector(self, 
                           vector: List[float],
                           top: int = 10,
                           select: Optional[List[str]] = None,
                           filter_query: Optional[str] = None) -> SearchResult:
        """
        Convenience method for vector-only search
        
        Args:
            vector: Vector for similarity search
            top: Number of results to return
            select: Fields to include in results
            filter_query: OData filter expression
            
        Returns:
            SearchResult: Search results with documents and count
        """
        return await self.search(
            vector=vector,
            search_type=SearchType.VECTOR_ONLY,
            top=top,
            select=select,
            filter_query=filter_query
        )
    
    async def search_text(self, 
                         search_text: str,
                         top: int = 10,
                         select: Optional[List[str]] = None,
                         filter_query: Optional[str] = None) -> SearchResult:
        """
        Convenience method for text-only search
        
        Args:
            search_text: Text query for search
            top: Number of results to return
            select: Fields to include in results
            filter_query: OData filter expression
            
        Returns:
            SearchResult: Search results with documents and count
        """
        return await self.search(
            search_text=search_text,
            search_type=SearchType.TEXT_ONLY,
            top=top,
            select=select,
            filter_query=filter_query
        )
