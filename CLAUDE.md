# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **event-driven Azure microservice architecture** that automatically processes files uploaded to blob storage, extracts content, generates embeddings with Azure OpenAI, and indexes them in Azure AI Search for semantic search. The system uses Service Bus for message queuing and KEDA for queue-based auto-scaling (0-3 replicas).

## Architecture

**Core Flow:**
```
Blob Storage → Event Grid → Service Bus Queue → Container Apps (KEDA scaled) → Processing → Azure OpenAI (embeddings) → Azure AI Search
```

**Two Main Services:**
1. **Indexer App** (`services/indexer_app/`) - Main file processing service
2. **MCP Server** (`services/mcp_server/`) - Model Context Protocol server for AI assistant integration with search

**Shared Libraries** (`shared/`) - Reusable modules for Azure clients, processing, utilities, and configuration

## Key Architectural Patterns

### Authentication & Token Management
- **All Azure services use Managed Identity** (no connection strings/secrets)
- Token caching with automatic refresh (`shared/azure_clients/auth.py`)
- Thread-safe token management with pre-warming capability
- Each Azure client extends `AzureClientBase` for consistent token handling
- Tokens expire after 45 minutes and are auto-refreshed 5 minutes before expiry

### Direct HTTP Clients (Not SDK-based)
All Azure services use custom HTTP clients with token authentication:
- `DirectBlobClient` - Blob storage operations
- `DirectSearchClient` - Azure AI Search indexing
- `DirectOpenAIClient` - Embedding generation with custom domain support
- `DirectServiceBusClient` - Queue message processing with lock renewal

**Why Direct HTTP?** Better control over retry logic, rate limiting, token management, and avoiding SDK version conflicts.

### Concurrency & Performance
- **Two-level concurrency model:**
  - `CONCURRENT_MESSAGE_PROCESSING` (default: 5) - Service Bus message processing
  - `CONCURRENT_FILE_PROCESSING` (default: 3) - Parallel embedding generation
- **KEDA auto-scaling:** 0-3 replicas based on queue depth (10 messages/replica trigger)
- **Message lock renewal:** Automatic lock extension for long-running documents
- **Token-aware chunking:** Preserves document structure while respecting token limits

### Document Processing Pipeline
1. **Extract** (`shared/processing/file_extractor.py`) - Extract content from TXT, PDF, DOCX, JSON, MD, CSV
2. **Chunk** (`shared/utils/chunking.py`) - Token-aware chunking with overlap (4K tokens/chunk, 200 token overlap)
3. **Embed** (`shared/azure_clients/openai_client.py`) - Generate 1536-dimension vectors (parallel batching)
4. **Index** (`shared/azure_clients/search_client.py`) - Upload to Azure AI Search with retry logic

### Error Handling & Retry Logic
- **Rate limiting:** Automatic backoff with exponential delays (respects `Retry-After` headers)
- **Permanent failures:** Skip retry on 400, 401, 403, 404, 405, 409, 422
- **Transient failures:** Retry with backoff (configurable max retries)
- **Dead letter queue:** Messages exceeding max delivery count move to DLQ
- Implemented in `shared/utils/retry.py`

## Common Development Tasks

### Deploy Infrastructure
```powershell
# Full deployment (infrastructure + indexer + MCP)
.\scripts\deploy-all.ps1

# Individual components
.\scripts\deploy-infrastructure.ps1
.\scripts\deploy-indexer.ps1
.\scripts\deploy-mcp.ps1

# Check status
.\scripts\get-deployment-status.ps1

# Validate infrastructure
.\scripts\validate-infrastructure.ps1
```

### Build and Test Locally
```bash
# Run tests for indexer service
cd services/indexer_app
pip install -r requirements-test.txt
pytest tests/ -v

# Run tests for MCP server
cd services/mcp_server
pip install -r requirements-test.txt
pytest tests/ -v

# Linting
flake8 app/ --count --max-line-length=127 --statistics

# Build Docker images
cd services/indexer_app
docker build -t indexer-app .

cd services/mcp_server
docker build -t mcp-server .
```

### View Logs
```bash
# Real-time logs
az containerapp logs show --name <app-name> --resource-group <rg-name> --follow

# Recent logs
az containerapp logs show --name <app-name> --resource-group <rg-name>
```

### Test Processing
```bash
# Upload test file
az storage blob upload \
  --file test.txt \
  --container-name landing \
  --name test.txt \
  --account-name <storage-account-name> \
  --auth-mode login

# Manual processing endpoint (development)
curl -X POST https://<app-url>/process \
  -H "Content-Type: application/json" \
  -d '{"container_name": "landing", "blob_name": "test.txt"}'

# Health check
curl https://<app-url>/health
```

## Configuration System

**All configuration in** `shared/config/settings.py`

Key configuration groups:
- **Azure Services:** Account names, endpoints, API versions
- **Authentication:** Token lifetimes, managed identity client ID
- **Processing:** Token limits, chunk sizes, file size limits
- **Concurrency:** Message and file processing parallelism
- **Service Bus:** Lock renewal, max delivery count, batch sizes
- **Retry Logic:** Max retries, delay intervals, rate limits
- **Logging:** Verbosity controls, token preview lengths

**Environment variables are read once at startup** - changes require container restart.

## File Structure

```
shared/                      # Shared libraries across services
├── azure_clients/          # Direct HTTP clients for Azure services
│   ├── auth.py            # Base token management (AzureClientBase)
│   ├── blob_client.py     # Blob storage operations
│   ├── openai_client.py   # Embedding generation
│   ├── search_client.py   # Azure AI Search indexing
│   └── servicebus_client.py # Queue message processing
├── processing/            # Document processing pipeline
│   ├── document_processor.py # Orchestrates full pipeline
│   └── file_extractor.py  # Content extraction by file type
├── services/              # Service Bus processing
│   └── servicebus_processor.py # Message handling & concurrency
├── utils/                 # Utilities
│   ├── chunking.py       # Token-aware chunking logic
│   ├── retry.py          # Retry and rate limit handling
│   └── exceptions.py     # Custom exception classes
└── config/
    └── settings.py       # All configuration constants

services/indexer_app/      # Main file processing service
├── app/
│   ├── main.py           # Entry point, aiohttp server
│   └── api/handlers.py   # HTTP endpoints (health, process, webhook)
└── Dockerfile            # Container definition

services/mcp_server/       # Model Context Protocol server
├── app/
│   └── app.py            # MCP server with JWT auth & search tools
└── Dockerfile

scripts/                   # PowerShell deployment scripts
├── deploy-all.ps1        # Deploy everything
├── deploy-infrastructure.ps1 # Azure resources
├── deploy-indexer.ps1    # Indexer container app
└── deploy-mcp.ps1        # MCP server container app

index_definiton/           # Azure AI Search schema
└── index.json            # Vector search index definition
```

## Modifying the Search Index

**Location:** `index_definiton/index.json`

The index uses HNSW vector search (1536 dimensions for `text-embedding-ada-002`):
- **id** (String, Key) - Document identifier (format: `{blob_name}_chunk_{n}`)
- **content** (String, Searchable) - Text content
- **vector** (Collection(Single), 1536 dims) - Embeddings for semantic search

**To modify:**
1. Edit `index_definiton/index.json`
2. Run `.\scripts\deploy-infrastructure.ps1` to recreate index
3. **Warning:** Recreating the index deletes all data

**To add fields:**
- Update JSON schema
- Modify `DocumentProcessor._create_search_documents()` in `shared/processing/document_processor.py` to populate new fields

## Service Bus Lock Management

**Problem:** Long-running document processing can exceed Service Bus lock timeout (default 30s)

**Solution:** Automatic lock renewal (`SERVICEBUS_LOCK_RENEWAL_ENABLED=true`)
- Renewal interval: 20 seconds (configurable)
- Renews lock until processing completes
- Implementation in `shared/services/servicebus_processor.py`

**Disable for fast processing** to reduce API calls.

## MCP Server Integration

The MCP server provides two search tools for AI assistants:
1. **perform_search** - Hybrid/text/vector search with filters
2. **get_all_docs** - List all documents

**Authentication:** Azure JWT tokens with tenant validation
**Endpoint:** `/messages` (HTTP transport)
**Excluded fields:** `vector` (too large for responses)

**Testing:**
```powershell
$token = az account get-access-token --tenant <tenant-id> --scope https://search.azure.com/.default --query accessToken --output tsv

# Test search
Invoke-RestMethod -Uri "https://<mcp-url>/messages" -Method Post -Body '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "perform_search", "arguments": {"search_text": "test", "authorization": "Bearer '$token'"}}}'
```

## Performance Tuning

**High-throughput (requires high Azure quotas):**
```bash
CONCURRENT_MESSAGE_PROCESSING=10
CONCURRENT_FILE_PROCESSING=5
CHUNK_MAX_TOKENS=2000
```

**Conservative (low quotas):**
```bash
CONCURRENT_MESSAGE_PROCESSING=2
CONCURRENT_FILE_PROCESSING=1
CHUNK_MAX_TOKENS=6000
SERVICEBUS_LOCK_RENEWAL_ENABLED=false
```

**Monitor rate limits** - Adjust concurrency if seeing 429 errors.

## Common Issues

| Issue | Solution |
|-------|----------|
| 429 Rate Limit Errors | Reduce `CONCURRENT_*` settings |
| Token acquisition timeout | Check managed identity RBAC assignments |
| Lock timeout errors | Enable `SERVICEBUS_LOCK_RENEWAL_ENABLED=true` |
| Memory issues | Reduce `CHUNK_MAX_TOKENS` or `MAX_FILE_SIZE_MB` |
| KEDA not scaling | Check Service Bus queue metrics |
| Duplicate processing | Ensure lock renewal is enabled for long files |

## CI/CD Pipeline

**GitHub Actions workflow** (`.github/workflows/ci-cd.yml`) automates the full deployment pipeline:

### Workflow Jobs
1. **test-indexer** - Linting and tests for indexer service
2. **test-mcp** - Linting and tests for MCP server
3. **build-and-push-indexer** - Build image → Push to ACR → Update Container App (main branch only)
4. **build-and-push-mcp** - Build image → Push to ACR → Update Container App (main branch only)
5. **notify-deployment** - Generate deployment summary with URLs

### Triggers
- **Push to `main`**: Full CI/CD (test → build → deploy)
- **Push to `develop`**: Tests only (no deployment)
- **Pull Requests**: Tests only

### Required GitHub Secrets
Set these in repository Settings → Secrets and variables → Actions:

| Secret | Description | How to Get |
|--------|-------------|------------|
| `AZURE_CREDENTIALS` | Service principal JSON | `az ad sp create-for-rbac --sdk-auth` |
| `AZURE_REGISTRY` | ACR name (without .azurecr.io) | From Azure Portal |
| `AZURE_RESOURCE_GROUP` | Resource group name | From deployment scripts |
| `INDEXER_APP_NAME` | Indexer container app name | From deployment scripts |
| `MCP_SERVER_APP_NAME` | MCP server container app name | From deployment scripts |

### Setup Service Principal
```bash
az ad sp create-for-rbac \
  --name "github-actions-blob-crawler" \
  --role contributor \
  --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group-name} \
  --sdk-auth
```

Copy entire JSON output as `AZURE_CREDENTIALS` secret. The service principal also needs `AcrPush` role on the container registry.

### Deployment Flow
1. Tests run on every commit
2. On `main` branch: builds Docker images with commit SHA tags
3. Pushes to Azure Container Registry
4. Updates Container Apps with new image
5. Verifies deployment via `/health` endpoints
6. Posts deployment summary with service URLs

**View results**: Actions tab → Workflow run → Job summary

## Development Notes

- **Python 3.11+** required (uses modern async patterns)
- **Tests run in CI/CD** - basic import tests validate dependencies
- **All services are stateless** - designed for horizontal scaling
- **Logging is verbose by default** - adjust with `VERBOSE_*` settings
- **Container Apps restart on config changes** - no hot reload
- **Docker images tagged with git SHA** - enables rollback via image tags