# Azure Search MCP Server

This MCP (Model Context Protocol) server provides search capabilities using Azure AI Search with JWT token authentication and configurable filtering.

## Features

- **Azure AI Search Integration**: Uses your existing Azure Search client to query indexed documents
- **JWT Token Authentication**: Validates Azure tokens and checks tenant ID
- **Flexible Filtering**: Supports Azure Search filter expressions for field-based filtering
- **Configurable Results**: Excludes vector fields and allows field selection
- **MCP Protocol**: Implements proper MCP server for integration with MCP clients

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

## MCP Tool: azure_search

### Parameters

- `query` (string, optional): Search query text for full-text search
- `filters` (object, optional): Dictionary of field names to Azure Search filter expressions
- `top` (integer, optional): Number of results to return (1-100, default: 10)
- `select_fields` (array, optional): Specific fields to include in results
- `authorization` (string, required): Bearer token for authentication

### Example Usage

#### Text Search with Filters
```json
{
  "name": "azure_search",
  "arguments": {
    "query": "artificial intelligence",
    "filters": {
      "category": "eq 'technology'",
      "publishedDate": "ge 2023-01-01"
    },
    "top": 5,
    "authorization": "Bearer eyJ0eXAiOiJKV1Q..."
  }
}
```

#### Filter-Only Search
```json
{
  "name": "azure_search",
  "arguments": {
    "filters": {
      "status": "eq 'published'",
      "author": "eq 'John Doe'"
    },
    "top": 10,
    "select_fields": ["id", "title", "content", "author"],
    "authorization": "Bearer eyJ0eXAiOiJKV1Q..."
  }
}
```

## Azure Search Filter Expressions

The `filters` parameter accepts Azure Search OData filter expressions:

- **Exact match**: `"eq 'value'"`
- **Not equal**: `"ne 'value'"`
- **Comparisons**: `"gt 100"`, `"ge 50"`, `"lt 1000"`, `"le 500"`
- **In list**: `"search.in('value1,value2,value3')"`
- **Text search**: `"search.ismatch('keyword')"`
- **Date range**: `"ge 2023-01-01 and le 2023-12-31"`
- **Multiple conditions**: `"eq 'published' and ge 2023-01-01"`
- **Null checks**: `"eq null"`, `"ne null"`

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

## Development

### Local Testing

1. Set required environment variables
2. Install dependencies: `pip install -r requirements.txt`
3. Run the server: `python app/app.py`
4. Test with: `python test_mcp_server.py`

### Docker Deployment

The server is designed to run in Azure Container Apps with:

- Managed identity authentication
- Shared volume for common modules
- Environment variables from deployment configuration

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
