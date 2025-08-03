"""
MCP Server - Azure AI Search Integration using FastMCP and SSE

This MCP server provides search capabilities using Azure AI Search with
JWT token authentication and configurable filtering using SSE transport.
"""

import asyncio
import logging
import sys
import os
import json
from typing import List, Dict, Any, Optional
import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from contextvars import ContextVar

# Add the shared directory to the Python path
shared_path = '/app/shared' if os.path.exists('/app/shared') else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'shared')
sys.path.insert(0, shared_path)

# Import shared modules
from azure_clients.search_client import DirectSearchClient
from azure_clients.openai_client import DirectOpenAIClient
from azure_clients.auth import create_credential
from config.settings import (
    SEARCH_SERVICE_NAME, SEARCH_INDEX_NAME, AZURE_SEARCH_SCOPE, 
    SEARCH_ENDPOINT_SUFFIX, AZURE_TENANT_ID, MCP_SERVER_NAME, 
    MCP_SERVER_VERSION, SEARCH_DEFAULT_TOP, SEARCH_MAX_TOP, 
    EXCLUDED_FIELDS, MCP_PORT, OPENAI_SERVICE_NAME, AZURE_COGNITIVE_SCOPE,
    OPENAI_ENDPOINT_BASE, OPENAI_EMBEDDING_MODEL
)

# Import authentication module
from auth.jwt_validator import validate_bearer_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(MCP_SERVER_NAME)

# Global clients
search_client: Optional[DirectSearchClient] = None
openai_client: Optional[DirectOpenAIClient] = None

# Context variable to store the current request's authorization header
current_authorization: ContextVar[str] = ContextVar('current_authorization', default="")


async def initialize_search_client():
    """Initialize the Azure Search client"""
    global search_client
    
    try:
        if not SEARCH_SERVICE_NAME:
            raise ValueError("AZURE_SEARCH_SERVICE_NAME environment variable not set")
        
        if not SEARCH_INDEX_NAME:
            raise ValueError("AZURE_SEARCH_INDEX_NAME environment variable not set")
        
        # Get Azure credential
        credential = create_credential()
        
        # Build search endpoint
        search_endpoint = f"https://{SEARCH_SERVICE_NAME}{SEARCH_ENDPOINT_SUFFIX}"
        
        # Create search client
        search_client = DirectSearchClient(
            endpoint=search_endpoint,
            credential=credential,
            scope=AZURE_SEARCH_SCOPE,
            index_name=SEARCH_INDEX_NAME
        )
        
        logger.info(f"Search client initialized - Endpoint: {search_endpoint}, Index: {SEARCH_INDEX_NAME}")
        
    except Exception as e:
        logger.error(f"Failed to initialize search client: {e}")
        raise


async def initialize_openai_client():
    """Initialize the Azure OpenAI client"""
    global openai_client
    
    try:
        if not OPENAI_SERVICE_NAME:
            raise ValueError("AZURE_OPENAI_SERVICE_NAME environment variable not set")
        
        # Get Azure credential
        credential = create_credential()
        
        # Create OpenAI client
        openai_client = DirectOpenAIClient(
            endpoint=OPENAI_ENDPOINT_BASE,
            credential=credential,
            scope=AZURE_COGNITIVE_SCOPE
        )
        
        logger.info(f"OpenAI client initialized - Endpoint: {OPENAI_ENDPOINT_BASE}, Model: {OPENAI_EMBEDDING_MODEL}")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        raise


@mcp.tool()
async def azure_search(
    query: Optional[str] = None,
    filters: Optional[Dict[str, str]] = None,
    top: Optional[int] = SEARCH_DEFAULT_TOP,
    select_fields: Optional[List[str]] = None,
    search_type: Optional[str] = "text"
) -> str:
    """
    Search Azure AI Search index with optional filters.
    Authentication via Authorization header as per MCP spec.
    
    Args:
        query: Search query text (optional for filter-only searches)
        filters: Dictionary of field names to Azure Search filter expressions
        top: Number of results to return (max {SEARCH_MAX_TOP})
        select_fields: Specific fields to include in results (optional)
        search_type: Type of search - "text", "vector", or "hybrid" (default: "text")
    """
    try:
        # Get authorization header from context
        authorization = current_authorization.get()
        
        # Validate authentication token
        if not authorization:
            return "Error: Missing Authorization header. Please provide Bearer token in Authorization header as per MCP spec."
        
        # Validate JWT token and extract user info
        if not AZURE_TENANT_ID:
            return "Error: Azure tenant ID not configured"
        
        try:
            user_info = validate_bearer_token(authorization, AZURE_TENANT_ID)
            logger.info(f"Authenticated user: {user_info.get('username', 'unknown')}")
        except ValueError as e:
            return f"Authentication failed: {str(e)}"
        
        # Initialize clients if needed
        if not search_client:
            await initialize_search_client()
        
        # Initialize OpenAI client if we need embeddings for vector or hybrid search
        if search_type in ["vector", "hybrid"] and not openai_client:
            await initialize_openai_client()
        
        # Build filter query from filters dict
        filter_query = None
        if filters:
            filter_parts = []
            for field, value in filters.items():
                # Assume the value is already a proper Azure Search filter expression
                filter_parts.append(f"{field} {value}")
            filter_query = " and ".join(filter_parts)
        
        # Ensure top doesn't exceed maximum
        top = min(top or SEARCH_DEFAULT_TOP, SEARCH_MAX_TOP)
        
        # Validate search type and requirements
        if search_type not in ["text", "vector", "hybrid"]:
            return f"Error: Invalid search_type '{search_type}'. Must be one of: text, vector, hybrid"
        
        if search_type in ["vector", "hybrid"] and not query:
            return "Error: 'query' is required for vector and hybrid search types"
        
        # Generate embeddings if needed for vector or hybrid search
        vector_embeddings = None
        if search_type in ["vector", "hybrid"] and query:
            try:
                logger.info(f"Generating embeddings for query: '{query}'")
                vector_embeddings = await openai_client.create_embeddings(query, OPENAI_EMBEDDING_MODEL)
                logger.info(f"Generated embeddings with {len(vector_embeddings)} dimensions")
            except Exception as e:
                logger.error(f"Failed to generate embeddings: {e}")
                return f"Error: Failed to generate embeddings for query: {str(e)}"
        
        # Perform search based on type
        logger.info(f"Performing {search_type} search - Query: '{query}', Filter: '{filter_query}', Top: {top}")
        
        if search_type == "text":
            if query:
                # Text search with optional filters
                search_result = await search_client.search_text(
                    search_text=query,
                    top=top,
                    select=select_fields,
                    filter_query=filter_query
                )
            else:
                # Filter-only search (no text query)
                if not filter_query:
                    return "Error: Either 'query' or 'filters' must be provided for text search"
                
                # Use empty search with filters
                search_result = await search_client.search_text(
                    search_text="*",  # Match all documents
                    top=top,
                    select=select_fields,
                    filter_query=filter_query
                )
        elif search_type == "vector":
            # Vector-only search
            search_result = await search_client.search_vector(
                vector=vector_embeddings,
                top=top,
                select=select_fields,
                filter_query=filter_query
            )
        elif search_type == "hybrid":
            # Hybrid search (text + vector)
            search_result = await search_client.search_hybrid(
                search_text=query,
                vector=vector_embeddings,
                top=top,
                select=select_fields,
                filter_query=filter_query
            )
        
        # Filter out excluded fields from results
        filtered_documents = []
        for doc in search_result.documents:
            filtered_doc = {k: v for k, v in doc.items() if k not in EXCLUDED_FIELDS}
            filtered_documents.append(filtered_doc)
        
        # Format response
        response = {
            "total_count": search_result.count,
            "returned_count": len(filtered_documents),
            "documents": filtered_documents,
            "query": query,
            "search_type": search_type,
            "filters": filters,
            "embeddings_generated": vector_embeddings is not None,
            "user": user_info.get('username', 'unknown')
        }
        
        return json.dumps(response, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return f"Search failed: {str(e)}"


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided MCP server with SSE."""
    sse = SseServerTransport("/messages")
    
    async def handle_sse(request: Request):
        """Handle SSE connections for MCP protocol"""
        # Extract Authorization header
        auth_header = request.headers.get('authorization', '')
        
        # Set the authorization header in context for tool access
        current_authorization.set(auth_header)
        
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )
    
    async def health_check(request: Request):
        """Health check endpoint"""
        return JSONResponse({
            'status': 'healthy',
            'service': 'mcp-server',
            'version': MCP_SERVER_VERSION,
            'tenant_configured': bool(AZURE_TENANT_ID),
            'search_configured': bool(SEARCH_SERVICE_NAME),
            'openai_configured': bool(OPENAI_SERVICE_NAME),
            'vector_search_available': bool(openai_client),
            'hybrid_search_available': bool(openai_client),
            'transport': 'SSE'
        })
    
    async def ready_check(request: Request):
        """Readiness check endpoint"""
        return JSONResponse({
            'status': 'ready',
            'service': 'mcp-server',
            'mcp_server_name': MCP_SERVER_NAME,
            'version': MCP_SERVER_VERSION,
            'search_types_available': ['text'] + (['vector', 'hybrid'] if openai_client else []),
            'transport': 'SSE'
        })
    
    async def handle_post_message(request: Request):
        """Handle POST messages for MCP protocol with authorization"""
        # Extract Authorization header
        auth_header = request.headers.get('authorization', '')
        
        # Set the authorization header in context for tool access
        current_authorization.set(auth_header)
        
        # Delegate to the SSE transport's POST handler
        return await sse.handle_post_message(request)
    
    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/health", endpoint=health_check),
            Route("/ready", endpoint=ready_check),
            Route("/", endpoint=health_check),
            Route("/messages", endpoint=handle_post_message, methods=["POST"]),
        ],
    )


async def main():
    """
    Main entry point for the MCP Server
    """
    logger.info(f"Starting MCP Server: {MCP_SERVER_NAME} v{MCP_SERVER_VERSION}")
    
    # Validate configuration
    if not AZURE_TENANT_ID:
        logger.error("AZURE_TENANT_ID environment variable not set. Token validation will fail.")
        logger.info("This should be set during infrastructure deployment.")
    
    if not SEARCH_SERVICE_NAME:
        logger.error("AZURE_SEARCH_SERVICE_NAME environment variable not set")
        sys.exit(1)
    
    if not OPENAI_SERVICE_NAME:
        logger.warning("AZURE_OPENAI_SERVICE_NAME environment variable not set. Vector and hybrid search will not be available.")
    
    # Initialize search client
    await initialize_search_client()
    
    # Initialize OpenAI client if configured
    if OPENAI_SERVICE_NAME:
        try:
            await initialize_openai_client()
        except Exception as e:
            logger.warning(f"OpenAI client initialization failed: {e}. Vector and hybrid search will not be available.")
    
    # Get the MCP server from FastMCP
    mcp_server = mcp._mcp_server
    
    # Create Starlette app with SSE transport
    app = create_starlette_app(mcp_server, debug=False)
    
    logger.info(f"Starting HTTP server on port {MCP_PORT}")
    logger.info(f"Health check: http://localhost:{MCP_PORT}/health")
    logger.info(f"Ready check: http://localhost:{MCP_PORT}/ready")
    logger.info(f"SSE endpoint: http://localhost:{MCP_PORT}/sse")
    logger.info("MCP server is ready to handle search requests via SSE")
    logger.info(f"Configured for tenant: {AZURE_TENANT_ID}")
    logger.info(f"Search service: {SEARCH_SERVICE_NAME}")
    logger.info(f"Search index: {SEARCH_INDEX_NAME}")
    if OPENAI_SERVICE_NAME:
        logger.info(f"OpenAI service: {OPENAI_SERVICE_NAME}")
        logger.info(f"Embedding model: {OPENAI_EMBEDDING_MODEL}")
        logger.info("Vector and hybrid search available")
    else:
        logger.info("OpenAI service not configured - only text search available")
    
    # Run the server
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=MCP_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == '__main__':
    asyncio.run(main())
