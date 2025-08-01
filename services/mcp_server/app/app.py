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

# Add the shared directory to the Python path
shared_path = '/app/shared' if os.path.exists('/app/shared') else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'shared')
sys.path.insert(0, shared_path)

# Import shared modules
from azure_clients.search_client import DirectSearchClient
from azure_clients.auth import create_credential
from config.settings import (
    SEARCH_SERVICE_NAME, SEARCH_INDEX_NAME, AZURE_SEARCH_SCOPE, 
    SEARCH_ENDPOINT_SUFFIX, AZURE_TENANT_ID, MCP_SERVER_NAME, 
    MCP_SERVER_VERSION, SEARCH_DEFAULT_TOP, SEARCH_MAX_TOP, 
    EXCLUDED_FIELDS, MCP_PORT
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

# Global search client
search_client: Optional[DirectSearchClient] = None


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


@mcp.tool()
async def azure_search(
    query: Optional[str] = None,
    filters: Optional[Dict[str, str]] = None,
    top: Optional[int] = SEARCH_DEFAULT_TOP,
    select_fields: Optional[List[str]] = None,
    authorization: str = ""
) -> str:
    """
    Search Azure AI Search index with optional filters and authentication.
    
    Args:
        query: Search query text (optional for filter-only searches)
        filters: Dictionary of field names to Azure Search filter expressions
        top: Number of results to return (max {SEARCH_MAX_TOP})
        select_fields: Specific fields to include in results (optional)
        authorization: Bearer token for authentication (required)
    """
    try:
        # Validate authentication token
        if not authorization:
            return "Error: Missing authorization token"
        
        # Validate JWT token and extract user info
        if not AZURE_TENANT_ID:
            return "Error: Azure tenant ID not configured"
        
        try:
            user_info = validate_bearer_token(authorization, AZURE_TENANT_ID)
            logger.info(f"Authenticated user: {user_info.get('username', 'unknown')}")
        except ValueError as e:
            return f"Authentication failed: {str(e)}"
        
        # Initialize search client if needed
        if not search_client:
            await initialize_search_client()
        
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
        
        # Perform search
        logger.info(f"Performing search - Query: '{query}', Filter: '{filter_query}', Top: {top}")
        
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
                return "Error: Either 'query' or 'filters' must be provided"
            
            # Use empty search with filters
            search_result = await search_client.search_text(
                search_text="*",  # Match all documents
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
            "filters": filters,
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
            'transport': 'SSE'
        })
    
    async def ready_check(request: Request):
        """Readiness check endpoint"""
        return JSONResponse({
            'status': 'ready',
            'service': 'mcp-server',
            'mcp_server_name': MCP_SERVER_NAME,
            'version': MCP_SERVER_VERSION,
            'transport': 'SSE'
        })
    
    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/health", endpoint=health_check),
            Route("/ready", endpoint=ready_check),
            Route("/", endpoint=health_check),
            Mount("/messages", app=sse.handle_post_message),
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
    
    # Initialize search client
    await initialize_search_client()
    
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
