# Azure Search MCP Server

This MCP (Model Context Protocol) server provides search capabilities using Azure AI Search with JWT token authentication. Successfully deployed and tested on Azure Container Apps.

## Features

- **Azure AI Search Integration**: Direct search access to your indexed documents
- **JWT Token Authentication**: Validates Azure tokens and checks tenant ID
- **Two Search Tools**: `perform_search` for queries and `get_all_docs` for document listing
- **HTTP Transport**: Uses standard HTTP instead of SSE for better reliability
- **MCP Protocol**: Fully compliant MCP server for integration with AI assistants

## Configuration

The server requires the following environment variables (automatically set during deployment):

```bash
# Azure Services
AZURE_SEARCH_SERVICE_NAME=your-search-service
AZURE_SEARCH_INDEX_NAME=documents
AZURE_TENANT_ID=your-tenant-id

# MCP Server Settings
MCP_SERVER_NAME=azure-search-mcp
MCP_SERVER_VERSION=1.0.0
MCP_PORT=8080
SEARCH_DEFAULT_TOP=10
SEARCH_MAX_TOP=100
EXCLUDED_FIELDS=vector
```

## MCP Tools

### 1. perform_search
Search Azure AI Search index with text queries and filters.

**Parameters:**
- `search_text` (string, optional): Search query text
- `search_type` (string): "hybrid", "text", or "vector" (default: "hybrid")
- `top` (integer): Number of results (default: 10, max: 100)
- `select` (array, optional): Specific fields to return
- `filter_query` (string, optional): Azure Search OData filter expression
- `authorization` (string, required): Bearer token

### 2. get_all_docs
Retrieve all documents from the index with optional limiting.

**Parameters:**
- `top` (integer, optional): Number of documents to return. If not specified, returns ALL documents
- `select` (array, optional): Fields to include (default: ["id"])
- `authorization` (string, required): Bearer token

### Example Usage
```json
{
  "name": "perform_search",
  "arguments": {
    "search_text": "artificial intelligence",
    "filter_query": "category eq 'technology'",
    "top": 5,
    "authorization": "Bearer eyJ0eXAiOiJKV1Q..."
  }
}
```

```json
{
  "name": "get_all_docs", 
  "arguments": {
    "top": 10,
    "select": ["id", "title", "content"],
    "authorization": "Bearer eyJ0eXAiOiJKV1Q..."
  }
}
```

## Azure Search Filter Expressions

The `filter_query` parameter accepts Azure Search OData filter expressions as strings:

- **Exact match**: `"category eq 'technology'"`
- **Not equal**: `"status ne 'draft'"`
- **Comparisons**: `"score gt 100"`, `"price le 500"`
- **Date range**: `"publishedDate ge 2023-01-01"`
- **Multiple conditions**: `"status eq 'published' and publishedDate ge 2023-01-01"`
- **In operator**: `"category in ('tech', 'science')"`
- **Null checks**: `"description ne null"`

## Azure Search Filter Expressions

The `filter_query` parameter accepts Azure Search OData filter expressions as strings:

- **Exact match**: `"category eq 'technology'"`
- **Not equal**: `"status ne 'draft'"`
- **Comparisons**: `"score gt 100"`, `"price le 500"`
- **Date range**: `"publishedDate ge 2023-01-01"`
- **Multiple conditions**: `"status eq 'published' and publishedDate ge 2023-01-01"`
- **In operator**: `"category in ('tech', 'science')"`
- **Null checks**: `"description ne null"`

## Authentication

The server validates Azure JWT tokens with the following requirements:

1. **Bearer Token Format**: `Authorization: Bearer <jwt_token>`
2. **Tenant Validation**: Token issuer must match configured Azure tenant ID
3. **Token Validation**: Standard JWT validation (signature, expiration, etc.)
4. **Token Structure**: Expected Azure token format with `iss` field containing tenant ID

Example token payload:
```json
{
  "aud": "https://graph.microsoft.com",
  "iss": "https://sts.windows.net/cf36141c-ddd7-45a7-b073-111f66d0b30c/",
  "oid": "user-object-id",
  "upn": "user@domain.com",
  "tid": "cf36141c-ddd7-45a7-b073-111f66d0b30c"
}
```

## Response Format

```json
{
  "total_count": 150,
  "returned_count": 10,
  "documents": [
    {
      "id": "doc1",
      "title": "AI Research Paper",
      "content": "Abstract text...",
      "author": "Dr. Smith",
      "publishedDate": "2023-06-15"
    }
  ],
  "query": "artificial intelligence",
  "filters": {"category": "eq 'technology'"},
  "user": "user@domain.com"
}
```

## Health Endpoints

- `GET /health`: Health check with configuration status
- `GET /ready`: Readiness check  
- `GET /`: Root endpoint (same as health)
- `POST /messages`: MCP protocol endpoint for tool calls

## Deployment

The server is deployed on Azure Container Apps at:
- **URL**: `https://mcp-server.blackwave-42d54423.eastus2.azurecontainerapps.io`
- **Protocol**: HTTP transport on `/messages` endpoint
- **Authentication**: Azure managed identity with tenant validation

Deploy using: `.\scripts\deploy-mcp.ps1`

## Error Handling

The server returns appropriate error messages for:

- Missing or invalid authentication tokens
- Tenant ID mismatches
- Invalid search parameters
- Azure Search API errors
- Configuration issues

## Security

- JWT token validation with signature verification
- Tenant ID verification against configured tenant
- Exclusion of sensitive fields (vector embeddings)
- Proper error handling without information leakage
