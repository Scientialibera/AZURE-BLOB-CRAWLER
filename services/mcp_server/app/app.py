import asyncio
import logging
import os
import sys
import json
from typing import Optional, Dict, List

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp import Context
from starlette.responses import JSONResponse

from azure_clients.search_client import DirectSearchClient
from azure_clients.openai_client import DirectOpenAIClient
from azure_clients.auth import create_credential
from auth.jwt_validator import validate_bearer_token

from config.settings import (
    SEARCH_SERVICE_NAME, SEARCH_INDEX_NAME, AZURE_SEARCH_SCOPE, SEARCH_ENDPOINT_SUFFIX,
    AZURE_TENANT_ID, MCP_SERVER_NAME, MCP_SERVER_VERSION,
    SEARCH_DEFAULT_TOP, SEARCH_MAX_TOP, SEARCH_ALL_DOCS_MAX, EXCLUDED_FIELDS, MCP_PORT,
    OPENAI_SERVICE_NAME, AZURE_COGNITIVE_SCOPE,
    OPENAI_ENDPOINT_BASE, OPENAI_EMBEDDING_MODEL
)

# ────────────────────────── Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────── MCP Init
mcp = FastMCP(name=MCP_SERVER_NAME)

# ────────────────────────── Global Clients
search_client: Optional[DirectSearchClient] = None
openai_client: Optional[DirectOpenAIClient] = None


# ────────────────────────── Helpers
def get_bearer_token() -> str:
    headers = get_http_headers()
    return headers.get("authorization", "")

async def initialize_search_client():
    global search_client
    if not search_client:
        credential = create_credential()
        search_client = DirectSearchClient(
            endpoint=f"https://{SEARCH_SERVICE_NAME}{SEARCH_ENDPOINT_SUFFIX}",
            credential=credential,
            scope=AZURE_SEARCH_SCOPE,
            index_name=SEARCH_INDEX_NAME
        )

async def initialize_openai_client():
    global openai_client
    if not openai_client:
        credential = create_credential()
        openai_client = DirectOpenAIClient(
            endpoint=OPENAI_ENDPOINT_BASE,
            credential=credential,
            scope=AZURE_COGNITIVE_SCOPE
        )

# ────────────────────────── Tool
@mcp.tool()
async def azure_search(
    query: Optional[str] = None,
    filters: Optional[Dict[str, str]] = None,
    top: Optional[int] = SEARCH_DEFAULT_TOP,
    select_fields: Optional[List[str]] = None,
    search_type: Optional[str] = "text",
    ctx: Context = None
) -> str:
    auth = get_bearer_token()
    if not auth:
        return "Error: Missing Authorization header"
    try:
        user_info = validate_bearer_token(auth, AZURE_TENANT_ID)
    except Exception as e:
        return f"Authentication failed: {str(e)}"

    await initialize_search_client()

    if search_type in ("vector", "hybrid"):
        if not query:
            return "Error: 'query' is required for vector or hybrid search"
        await initialize_openai_client()
        try:
            embeddings = await openai_client.create_embeddings(query, OPENAI_EMBEDDING_MODEL)
        except Exception as e:
            return f"Embedding error: {str(e)}"
    else:
        embeddings = None

    filter_query = " and ".join(f"{k} {v}" for k, v in filters.items()) if filters else None
    top = min(top or SEARCH_DEFAULT_TOP, SEARCH_MAX_TOP)

    try:
        if search_type == "text":
            result = await search_client.search_text(
                search_text=query or "*",
                top=top,
                select=select_fields,
                filter_query=filter_query
            )
        elif search_type == "vector":
            result = await search_client.search_vector(
                vector=embeddings,
                top=top,
                select=select_fields,
                filter_query=filter_query
            )
        elif search_type == "hybrid":
            result = await search_client.search_hybrid(
                search_text=query,
                vector=embeddings,
                top=top,
                select=select_fields,
                filter_query=filter_query
            )
        else:
            return f"Invalid search_type: {search_type}"
    except Exception as e:
        return f"Search failed: {str(e)}"

    docs = [{k: v for k, v in doc.items() if k not in EXCLUDED_FIELDS} for doc in result.documents]
    return json.dumps({
        "total_count": result.count,
        "returned_count": len(docs),
        "documents": docs,
        "query": query,
        "user": user_info.get("username", "unknown"),
        "search_type": search_type
    }, indent=2, default=str)


@mcp.tool()
async def get_all_docs(
    max_docs: Optional[int] = SEARCH_ALL_DOCS_MAX,
    ctx: Context = None
) -> str:
    """Get all document IDs from the search index using a wildcard search."""
    auth = get_bearer_token()
    if not auth:
        return "Error: Missing Authorization header"
    
    try:
        user_info = validate_bearer_token(auth, AZURE_TENANT_ID)
    except Exception as e:
        return f"Authentication failed: {str(e)}"

    await initialize_search_client()

    # Limit the number of documents to retrieve
    top = min(max_docs or SEARCH_ALL_DOCS_MAX, SEARCH_ALL_DOCS_MAX)

    try:
        # Perform a wildcard search to get all documents, selecting only the ID field
        result = await search_client.search_text(
            search_text="*",  # Wildcard to match all documents
            top=top,
            select=["id"],  # Only return the ID field
            filter_query=None
        )
    except Exception as e:
        return f"Search failed: {str(e)}"

    # Extract only the IDs from the results
    document_ids = [doc.get("id") for doc in result.documents if doc.get("id")]

    return json.dumps({
        "total_count": result.count,
        "returned_count": len(document_ids),
        "document_ids": document_ids,
        "user": user_info.get("username", "unknown"),
        "max_requested": top
    }, indent=2, default=str)


# ────────────────────────── Health Endpoint
@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    auth = get_bearer_token()
    if not auth:
        return "Error: Missing Authorization header"
    try:
        validate_bearer_token(auth, AZURE_TENANT_ID)
    except Exception as e:
        return f"Authentication failed: {str(e)}"
    
    return JSONResponse({
        "status": "healthy",
        "version": MCP_SERVER_VERSION,
        "search_configured": bool(SEARCH_SERVICE_NAME),
        "openai_enabled": bool(OPENAI_SERVICE_NAME),
        "transport": "http",
        "available_tools": ["azure_search", "get_all_docs"],
        "max_all_docs": SEARCH_ALL_DOCS_MAX
    })


# ────────────────────────── MCP Configuration Endpoint
@mcp.custom_route("/mcp-config", methods=["GET"])
async def mcp_config(request):
    """Return MCP server configuration for client discovery"""
    return JSONResponse({
        "mcpVersion": "2024-11-05",
        "name": MCP_SERVER_NAME,
        "version": MCP_SERVER_VERSION,
        "description": "Azure AI Search MCP server for semantic search and document retrieval",
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
            "logging": {}
        },
        "tools": [
            {
                "name": "azure_search",
                "description": "Search Azure AI Search index with text, vector, or hybrid search capabilities"
            },
            {
                "name": "get_all_docs", 
                "description": "Retrieve all document IDs from the search index"
            }
        ],
        "authentication": {
            "required": True,
            "type": "bearer",
            "description": "Requires Azure AD bearer token"
        }
    })


# ────────────────────────── Entry Point
async def main():
    logger.info(f"Starting MCP Server: {MCP_SERVER_NAME} (v{MCP_SERVER_VERSION})")
    await mcp.run_async(
        transport="http",
        host="0.0.0.0",
        port=MCP_PORT,
        path="/mcp",
        log_level="info"
    )


if __name__ == "__main__":
    asyncio.run(main())
