"""
Azure MCP Search Service

This is an MCP (Model Context Protocol) server that provides hybrid search capabilities
over Azure AI Search indexes using both text search and vector similarity search.

Features:
- Token-based authentication for secure access
- Hybrid search combining keyword and semantic search  
- Integration with Azure OpenAI for embedding generation
- RESTful API for search queries with filters
- Modular architecture following the same pattern as indexer-service
"""

import asyncio
import logging
import sys
import os
import requests
from aiohttp import web
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add shared modules to path
shared_path = os.path.join(os.path.dirname(__file__), 'shared')
if os.path.exists(shared_path):
    sys.path.append(shared_path)
else:
    # Fallback for development environment
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from config.settings import (
    MCP_HTTP_PORT, HTTP_HOST, HTTP_LOCALHOST, SEARCH_SERVICE_NAME,
    SEARCH_INDEX_NAME, OPENAI_SERVICE_NAME, MCP_SEARCH_TOKEN, 
    AZURE_CLIENT_ID, MAIN_LOOP_SLEEP_SECONDS, AZURE_TENANT_ID,
    AZURE_SEARCH_SCOPE, AZURE_COGNITIVE_SCOPE, SEARCH_ENDPOINT_SUFFIX,
    OPENAI_ENDPOINT_BASE, DOCUMENT_VECTOR_FIELD
)
from azure_clients import create_credential, DirectSearchClient, DirectOpenAIClient
from auth.jwt_auth import create_jwt_authenticator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MCPSearchService:
    """
    MCP Search Service for hybrid search operations
    
    This service provides hybrid search capabilities combining keyword search
    with vector similarity search using Azure AI Search and Azure OpenAI.
    """
    
    def __init__(self):
        """Initialize the MCP Search Service"""
        self.search_client: Optional[DirectSearchClient] = None
        self.openai_client: Optional[DirectOpenAIClient] = None
        self.credential = None
        
    async def initialize(self):
        """
        Initialize Azure clients with managed identity authentication
        """
        logger.info("Initializing MCP Search Service...")
        
        # Get managed identity credential
        self.credential = create_credential()
        
        # Initialize Search client
        if SEARCH_SERVICE_NAME:
            search_endpoint = f"https://{SEARCH_SERVICE_NAME}{SEARCH_ENDPOINT_SUFFIX}"
            self.search_client = DirectSearchClient(
                endpoint=search_endpoint,
                credential=self.credential,
                scope=AZURE_SEARCH_SCOPE,
                index_name=SEARCH_INDEX_NAME
            )
            logger.info(f"Search client initialized for endpoint: {search_endpoint}")
        else:
            logger.warning("Search service not configured")
            
        # Initialize OpenAI client  
        if OPENAI_SERVICE_NAME:
            self.openai_client = DirectOpenAIClient(
                endpoint=OPENAI_ENDPOINT_BASE,
                credential=self.credential,
                scope=AZURE_COGNITIVE_SCOPE
            )
            logger.info(f"OpenAI client initialized for endpoint: {OPENAI_ENDPOINT_BASE}")
        else:
            logger.warning("OpenAI service not configured")
            
        logger.info("MCP Search Service initialization complete")
    
    async def hybrid_search(self, query: str, filters: Optional[Dict[str, str]] = None, 
                          top: int = 10, skip: int = 0) -> Dict[str, Any]:
        """
        Perform hybrid search combining keyword and vector search
        
        Args:
            query: Search query string
            filters: Dictionary of field names to Azure Search filter expressions
            top: Number of results to return
            skip: Number of results to skip
            
        Returns:
            Dict[str, Any]: Combined search results
            
        Raises:
            Exception: If search operation fails
        """
        logger.info(f"Starting hybrid search for query: '{query}'")
        
        # Generate embedding for the query
        query_vector = None
        if self.openai_client and query.strip():
            try:
                logger.info(f"Generating embeddings for query: '{query[:50]}...'")
                query_vector = await self.openai_client.create_embeddings(query)
                logger.info(f"Successfully generated query embedding with {len(query_vector)} dimensions")
            except Exception as e:
                logger.warning(f"Failed to generate embedding for query: {e}")
                logger.warning("Falling back to text-only search")
        else:
            if not self.openai_client:
                logger.warning("OpenAI client not available - using text-only search")
            if not query.strip():
                logger.warning("Empty query - using text-only search")
        
        # Build filter string from filters dictionary
        filter_expressions = []
        if filters:
            for field_name, filter_expression in filters.items():
                if filter_expression and filter_expression.strip():
                    filter_expressions.append(filter_expression)
        
        combined_filter = " and ".join(filter_expressions) if filter_expressions else None
        
        # Perform search
        if self.search_client:
            # Exclude vector field from results to reduce response size
            select_fields = ['id', 'content']  # Only return essential fields, exclude vector
            
            if query_vector:
                # Hybrid search: combine text search with vector search
                logger.info("Performing hybrid search (text + vector)")
                search_results = await self._perform_hybrid_search(
                    query=query,
                    query_vector=query_vector,
                    filters=combined_filter,
                    top=top,
                    skip=skip,
                    select=select_fields
                )
            else:
                # Fallback to text-only search
                logger.info("Performing text-only search (no embeddings)")
                search_results = await self.search_client.search_documents(
                    query=query,
                    filters=combined_filter,
                    top=top,
                    skip=skip,
                    select=select_fields,
                    include_total_count=True,
                    search_mode="any",
                    query_type="simple"
                )
            
            # Add metadata about the search
            search_results['search_metadata'] = {
                'query': query,
                'filters_applied': combined_filter,
                'has_vector_search': query_vector is not None,
                'vector_dimensions': len(query_vector) if query_vector else 0,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Hybrid search completed. Found {len(search_results.get('value', []))} results")
            return search_results
        else:
            raise Exception("Search client not initialized")

    async def _perform_hybrid_search(self, query: str, query_vector: List[float], 
                                    filters: Optional[str] = None, top: int = 10, 
                                    skip: int = 0, select: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Perform hybrid search combining text and vector search
        
        Args:
            query: Text query for keyword search
            query_vector: Query vector for semantic search
            filters: OData filter expression
            top: Number of results to return
            skip: Number of results to skip
            select: Fields to return
            
        Returns:
            Dict[str, Any]: Combined search results
        """
        url = f"{self.search_client.endpoint}/indexes/{self.search_client.index_name}/docs/search?api-version={self.search_client.api_version}"
        headers = await self.search_client._get_headers()
        
        # Hybrid search payload combining text and vector search
        payload = {
            "search": query,
            "vectors": [
                {
                    "value": query_vector,
                    "fields": DOCUMENT_VECTOR_FIELD,  # Use the vector field from config
                    "k": top * 2  # Get more vector results for better hybrid ranking
                }
            ],
            "top": top,
            "skip": skip,
            "count": True,
            "searchMode": "any",
            "queryType": "simple"
        }
        
        if filters:
            payload["filter"] = filters
        if select:
            payload["select"] = ",".join(select)
            
        logger.info(f"Performing hybrid search - text: '{query}', vector dims: {len(query_vector)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code not in [200, 201]:
            logger.error(f"Hybrid search API error: {response.status_code}")
            logger.error(f"Response: {response.text}")
            response.raise_for_status()
        
        result = response.json()
        logger.info(f"Hybrid search successful - returned {len(result.get('value', []))} results")
        return result


class MCPAPIHandlers:
    """
    HTTP API handlers for the MCP Search Service
    
    This class provides all the HTTP endpoint handlers for JWT authentication,
    health checks, and search operations.
    """
    
    def __init__(self, search_service: MCPSearchService):
        """
        Initialize API handlers
        
        Args:
            search_service: MCP Search Service instance
        """
        self.search_service = search_service
        self.jwt_authenticator = create_jwt_authenticator()
        
        # Log authentication configuration
        if self.jwt_authenticator:
            logger.info("JWT authentication enabled")
        elif MCP_SEARCH_TOKEN:
            logger.info("Development token authentication enabled")
        else:
            logger.warning("No authentication configured!")
    
    def _validate_token(self, request) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate the authentication token (JWT or development token)
        
        Args:
            request: HTTP request object
            
        Returns:
            tuple[bool, Optional[Dict[str, Any]]]: (is_valid, user_info)
        """
        auth_header = request.headers.get('Authorization', '')
        
        # Check for Bearer token format
        if not auth_header.startswith('Bearer '):
            return False, None
            
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        # Try JWT authentication first (production)
        if self.jwt_authenticator:
            claims = self.jwt_authenticator.validate_token(token)
            if claims:
                user_info = self.jwt_authenticator.extract_user_info(claims)
                logger.info(f"JWT authentication successful for user: {user_info.get('username', 'unknown')}")
                return True, user_info
        
        # Fallback to development token (if configured)
        if MCP_SEARCH_TOKEN and token == MCP_SEARCH_TOKEN:
            logger.info("Development token authentication successful")
            return True, {'username': 'development-user', 'auth_type': 'development'}
        
        logger.warning("Token authentication failed")
        return False, None
    
    async def health_check(self, request):
        """
        Health check endpoint
        
        Returns:
            JSON response with service health status and configuration
        """
        return web.json_response({
            'status': 'healthy',
            'service': 'mcp-search-service',
            'timestamp': datetime.utcnow().isoformat(),
            'configuration': {
                'search_service': SEARCH_SERVICE_NAME,
                'search_index': SEARCH_INDEX_NAME,
                'openai_service': OPENAI_SERVICE_NAME,
                'port': MCP_HTTP_PORT
            }
        })
    
    async def readiness_check(self, request):
        """
        Readiness check endpoint
        
        Returns:
            JSON response with service readiness status
        """
        try:
            # Check if clients are initialized
            search_ready = self.search_service.search_client is not None
            openai_ready = self.search_service.openai_client is not None
            
            if not search_ready or not openai_ready:
                return web.json_response({
                    'status': 'not ready',
                    'message': 'Clients not initialized',
                    'clients': {
                        'search_client': search_ready,
                        'openai_client': openai_ready
                    }
                }, status=503)
            
            return web.json_response({
                'status': 'ready',
                'service': 'mcp-search-service',
                'timestamp': datetime.utcnow().isoformat(),
                'clients_initialized': True
            })
        except Exception as e:
            return web.json_response({'status': 'not ready', 'error': str(e)}, status=503)
    
    async def search(self, request):
        """
        Search endpoint with JWT/token authentication
        
        Query Parameters:
            - query: Search query string (required)
            - filters: JSON object with field names as keys and filter expressions as values
            - top: Number of results to return (default: 10)
            - skip: Number of results to skip (default: 0)
            
        Headers:
            - Authorization: Bearer <jwt-token> (required)
        
        Returns:
            JSON response with search results
        """
        # Validate authentication token
        is_valid, user_info = self._validate_token(request)
        if not is_valid:
            return web.json_response({
                'error': 'Invalid or missing authentication token',
                'message': 'Provide valid Bearer token in Authorization header'
            }, status=401)
        
        try:
            # Log user information (for audit purposes)
            username = user_info.get('username', 'unknown') if user_info else 'unknown'
            logger.info(f"Search request from user: {username}")
            
            # Extract query parameters
            query = request.query.get('query', '').strip()
            if not query:
                return web.json_response({
                    'error': 'Query parameter is required'
                }, status=400)
            
            # Parse filters parameter (JSON object)
            filters = {}
            filters_param = request.query.get('filters', '{}')
            if filters_param:
                try:
                    import json
                    filters = json.loads(filters_param)
                    if not isinstance(filters, dict):
                        raise ValueError("Filters must be a JSON object")
                except (json.JSONDecodeError, ValueError) as e:
                    return web.json_response({
                        'error': f'Invalid filters parameter: {e}'
                    }, status=400)
            
            # Parse pagination parameters
            try:
                top = int(request.query.get('top', '10'))
                skip = int(request.query.get('skip', '0'))
                
                if top < 1 or top > 1000:
                    raise ValueError("Top must be between 1 and 1000")
                if skip < 0:
                    raise ValueError("Skip must be non-negative")
                    
            except ValueError as e:
                return web.json_response({
                    'error': f'Invalid pagination parameter: {e}'
                }, status=400)
            
            # Perform hybrid search
            results = await self.search_service.hybrid_search(
                query=query,
                filters=filters,
                top=top,
                skip=skip
            )
            
            # Add user context to results
            if user_info:
                results['user_context'] = {
                    'username': username,
                    'auth_type': user_info.get('auth_type', 'jwt')
                }
            
            return web.json_response(results)
            
        except Exception as e:
            logger.error(f"Search request failed for user {username}: {e}")
            return web.json_response({
                'error': 'Search operation failed',
                'message': str(e)
            }, status=500)


def create_app(api_handlers: MCPAPIHandlers) -> web.Application:
    """
    Create the aiohttp application with all routes
    
    Args:
        api_handlers: API handlers instance
        
    Returns:
        web.Application: Configured aiohttp application
    """
    # Create app with increased header size limit for large JWT tokens
    app = web.Application(client_max_size=1024*1024*16)  # 16MB max request size
    
    # Add routes
    app.router.add_get('/health', api_handlers.health_check)
    app.router.add_get('/ready', api_handlers.readiness_check)
    app.router.add_get('/search', api_handlers.search)
    
    return app


async def main():
    """
    Main application entry point
    
    This function initializes all components and starts the HTTP server.
    """
    logger.info("Starting MCP Search Service...")
    logger.info(f"Configuration: "
               f"SEARCH_SERVICE={SEARCH_SERVICE_NAME}, "
               f"SEARCH_INDEX={SEARCH_INDEX_NAME}, "
               f"OPENAI_SERVICE={OPENAI_SERVICE_NAME}, "
               f"PORT={MCP_HTTP_PORT}")
    
    # Initialize the search service
    search_service = MCPSearchService()
    await search_service.initialize()
    
    # Initialize API handlers
    api_handlers = MCPAPIHandlers(search_service)
    
    # Create the web application
    app = create_app(api_handlers)
    
    # Start the web server with increased header limits
    runner = web.AppRunner(
        app,
        # Increase max header field size to handle large JWT tokens (default is 8190)
        max_field_size=65536  # 64KB for headers
    )
    await runner.setup()
    
    # Create TCPSite
    site = web.TCPSite(runner, HTTP_HOST, MCP_HTTP_PORT)
    await site.start()
    
    logger.info(f"MCP Search Service started on port {MCP_HTTP_PORT}")
    logger.info(f"Health check: http://{HTTP_LOCALHOST}:{MCP_HTTP_PORT}/health")
    logger.info(f"Ready check: http://{HTTP_LOCALHOST}:{MCP_HTTP_PORT}/ready")
    logger.info(f"Search endpoint: http://{HTTP_LOCALHOST}:{MCP_HTTP_PORT}/search")
    
    # Log authentication configuration
    if AZURE_TENANT_ID:
        logger.info(f"JWT authentication enabled for tenant: {AZURE_TENANT_ID}")
    elif MCP_SEARCH_TOKEN:
        logger.info("Development token authentication enabled")
    else:
        logger.warning("No authentication configured!")
    
    logger.info("MCP Search Service started successfully")
    
    # Keep the server running
    try:
        while True:
            await asyncio.sleep(MAIN_LOOP_SLEEP_SECONDS)
    except KeyboardInterrupt:
        logger.info("Shutting down MCP Search Service...")
    finally:
        # Clean shutdown
        await runner.cleanup()


if __name__ == '__main__':
    # Start the aiohttp application
    logger.info(f"Starting MCP Search Service on port {MCP_HTTP_PORT}")
    asyncio.run(main())