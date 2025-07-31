# Azure Event-Driven File Processing Pipeline + MCP Search Service

This solution implements a **high-performance, event-driven microservice architecture** on Azure that automatically processes files as they arrive in blob storage, plus a secure **MCP (Model Context Protocol) Search Service** for querying processed documents. The pipeline uses Azure Blob Storage, Event Grid, Service Bus, Container Apps, Azure OpenAI, and Azure AI Search.

## What's New

- **MCP Search Service**: Secure REST API for searching processed documents
- **Token Authentication**: Bearer token security for API access  
- **Hybrid Search**: Combines keyword and vector similarity search
- **Advanced Filtering**: Support for Azure Search filter expressions
- **Rich Metadata**: Returns relevance scores and search analytics
- **Microservice Architecture**: Two independent, scalable container apps

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Blob Storage  │───▶│   Event Grid    │───▶│  Service Bus    │
│    (Landing)    │    │  (BlobCreated)  │    │    (Queue)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Azure AI Search│◀───│   Indexer App   │◀───│  Service Bus    │
│  (Vector Index) │    │ (Container App) │    │ (Concurrent)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        ▲                         ▲
        │                         │
        │              ┌─────────────────┐
        │              │ Azure OpenAI    │
        │              │(Custom Domain)  │
        │              └─────────────────┘
        │
        │                         ┌─────────────────┐
        └─────────────────────────│ MCP Search API  │
                                  │ (Container App) │
                                  └─────────────────┘
```

## Key Features

### **High-Performance Processing**
- **Concurrent Message Processing**: Configurable parallel processing of Service Bus messages (default: 5 concurrent)
- **Concurrent Embedding Generation**: Parallel embedding creation for document chunks (default: 3 concurrent) 
- **Smart Rate Limiting**: Intelligent retry logic with automatic backoff for Azure

### **Intelligent Document Processing**
- **Token-Aware Chunking**: Preserves document structure while respecting token limits
- **Multi-Format Support**: TXT, PDF, DOCX, JSON, MD, CSV files
- **Page-Aware Processing**: Keeps PDF pages and DOCX sections intact when possible
- **Vector Embeddings**: Azure OpenAI integration for semantic search capabilities

### **Production-Ready Features**
- **Configurable Scaling**: Tune concurrency based on your Azure quotas
- **Detailed Telemetry**: Comprehensive logging with performance metrics
- **Manual Processing API**: Test endpoint for development and debugging

### **MCP Search Service**
- **Token-Based Authentication**: Secure API access using Bearer tokens
- **Hybrid Search**: Combines keyword search with vector similarity search
- **Real-Time Querying**: Direct access to processed documents via REST API
- **Advanced Filtering**: Support for Azure Search filter expressions
- **Production Ready**: Containerized service with health checks and monitoring

## Components

### **Core Infrastructure**
1. **Azure Blob Storage**: Landing zone for files to be processed
2. **Azure Event Grid**: Publishes blob creation events
3. **Azure Service Bus**: Reliable message queue for event processing
4. **Azure Container Apps**: Hosts both microservices (indexer + MCP search)
5. **Azure AI Search**: Indexes processed file content with vector embeddings
6. **Azure OpenAI**: Generates embeddings for semantic search capabilities
7. **Azure Container Registry**: Stores container images for both services

### **Microservices**
8. **Indexer Service** (`indexer-app`): Processes files and creates search indexes
   - Listens to Service Bus messages for new file events
   - Extracts content from various file formats
   - Generates embeddings using Azure OpenAI
   - Indexes documents in Azure AI Search

9. **MCP Search Service** (`mcp-search-app`): Provides secure search API
   - Token-based authentication for secure access
   - Hybrid search combining keyword and vector similarity
   - RESTful API for external applications
   - Real-time querying of processed documents

## Project Structure

```
AZURE-BLOB-CRAWLER/
├── 📁 ms/                              # Microservices
│   ├── 📁 indexer-service/             # File processing service
│   │   ├── indexer_server.py           # Main server application
│   │   ├── Dockerfile                  # Container definition
│   │   ├── requirements.txt            # Python dependencies
│   │   ├── 📁 api/                     # HTTP API handlers
│   │   │   └── handlers.py             # REST endpoints
│   │   ├── 📁 processing/              # Document processing
│   │   │   ├── document_processor.py   # Main processor
│   │   │   └── file_extractor.py       # File content extraction
│   │   └── 📁 services/                # Service integrations
│   │       └── servicebus_processor.py # Service Bus handling
│   │
│   ├── 📁 mcp-search-service/          # MCP Search API service
│   │   ├── mcp_search_server.py        # MCP search server
│   │   ├── Dockerfile                  # Container definition
│   │   └── requirements.txt            # Python dependencies
│   │
│   └── 📁 shared/                      # Shared libraries
│       ├── 📁 azure_clients/           # Azure service clients
│       │   ├── auth.py                 # Managed identity auth
│       │   ├── blob_client.py          # Blob storage client
│       │   ├── openai_client.py        # OpenAI API client
│       │   ├── search_client.py        # Azure Search client
│       │   └── servicebus_client.py    # Service Bus client
│       ├── 📁 config/                  # Configuration
│       │   └── settings.py             # Environment settings
│       └── 📁 utils/                   # Utilities
│           ├── chunking.py             # Text chunking logic
│           └── retry.py                # Retry mechanisms
│
├── 📁 scripts/                         # Deployment scripts
│   ├── deploy-all.ps1                  # Master deployment
│   ├── deploy-infrastructure.ps1       # Azure resources
│   ├── deploy-indexer.ps1            # Indexer service
│   ├── deploy-mcp-search.ps1          # MCP search service
│   ├── get-deployment-status.ps1       # Status checker
│   └── validate-infrastructure.ps1     # Infrastructure validator
│
├── 📁 docs/                            # Documentation
│   ├── CRUD_OPERATIONS.md             # Search API operations
│   └── MCP_SEARCH_SERVICE.md          # MCP service guide
│
├── 📁 examples/                        # Example code
│   ├── crud_examples.py               # Search examples
│   └── test_mcp_search.py             # MCP testing script
│
├── 📁 index_definiton/                # Search index schema
│   └── index.json                     # Azure Search index definition
│
├── deployment-config.json             # Deployment configuration
└── README.md                          # This file
```

## Supported File Types

- **Text Files**: `.txt`, `.md`, `.csv` - Direct text extraction
- **JSON Files**: `.json` - Structured data extraction with key-value context
- **PDF Files**: `.pdf` - Page-aware content extraction
- **Word Documents**: `.docx`, `.doc` - Section-aware content extraction

## Chunking Strategy

The service implements intelligent chunking based on file type:

- **Text Files**: Sentence-boundary aware chunking (doesn't break sentences)
- **PDF Files**: Page-aware chunking (keeps pages together when possible)
- **DOCX Files**: Section-aware chunking (keeps logical sections together)
- **Token Limits**: 
  - Processing chunks: 4,000 tokens (configurable)
  - Embedding chunks: 8,000 tokens (OpenAI limit)
  - Overlap: 200 tokens between chunks

## Quick Start

### Prerequisites

- **Azure CLI** installed and logged in (`az login`)
- **PowerShell** or **Bash** shell environment  
- **Azure subscription** with sufficient permissions for resource creation
- **Azure OpenAI** service with `text-embedding-ada-002` model deployed

### Automated Deployment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Scientialibera/AZURE-BLOB-CRAWLER.git
   cd AZURE-BLOB-CRAWLER
   ```

2. **Run the deployment script**:
   ```powershell
   # PowerShell
   .\scripts\deploy-all.ps1
   
   # Or use individual scripts
   .\scripts\deploy-infrastructure.ps1
   .\scripts\deploy-indexer.ps1
   ```

3. **Verify deployment**:
   ```powershell
   .\scripts\get-deployment-status.ps1
   ```

### Testing the Solution

1. **Upload a test document**:
   ```bash
   az storage blob upload \
     --file test-document.txt \
     --container-name landing \
     --name test-document.txt \
     --account-name <storage-account-name> \
     --auth-mode login
   ```

2. **Monitor processing**:
   ```bash
   # Check indexer service logs
   az containerapp logs show \
     --name indexer-app \
     --resource-group <resource-group>
   
   # Check indexer health endpoint  
   curl https://<indexer-app-url>/health
   ```

3. **Search processed documents** using MCP Search Service:
   ```bash
   # Basic search
   curl -X GET "https://<mcp-app-url>/search?query=your search terms" \
     -H "Authorization: Bearer "
   
   # Search with filters
   curl -X GET "https://<mcp-app-url>/search" \
     -H "Authorization: Bearer " \
     -G \
     --data-urlencode 'query=machine learning' \
     --data-urlencode 'filters={"content": "search.score() gt 0.5"}' \
     --data-urlencode 'top=10'
   ```

4. **Verify indexing in Azure AI Search**:
   - Navigate to Azure Portal → Search Service → Search Explorer
   - Query for your document content

## MCP Search Service

The **MCP (Model Context Protocol) Search Service** provides a secure, token-authenticated REST API for searching through processed documents using hybrid search capabilities.

### **Features**
- **Token Authentication**: Secure access using Bearer tokens
- **Hybrid Search**: Combines traditional keyword search with vector similarity
- **Real-time**: Direct querying of indexed documents
- **Advanced Filtering**: Support for Azure Search filter expressions
- **Rich Results**: Returns documents with relevance scores and metadata

### **API Endpoints**

#### Search Documents
```http
GET /search?query={query}&filters={filters}&top={top}&skip={skip}
Authorization: Bearer 
```

**Parameters:**
- `query` (required): Search query string
- `filters` (optional): JSON object with Azure Search filter expressions
- `top` (optional): Number of results (default: 10, max: 1000)
- `skip` (optional): Results to skip for pagination (default: 0)

#### Health Check
```http
GET /health
```
Returns service health and configuration status.

#### Readiness Check
```http
GET /ready
```
Returns client initialization status.

### **Example Usage**

```bash
# Basic search
curl -X GET "https://mcp-search-app.azurecontainerapps.io/search?query=machine learning" \
  -H "Authorization: Bearer "

# Advanced search with filters
curl -X GET "https://mcp-search-app.azurecontainerapps.io/search" \
  -H "Authorization: Bearer " \
  -G \
  --data-urlencode 'query=azure cloud' \
  --data-urlencode 'filters={"content": "search.score() gt 0.7"}' \
  --data-urlencode 'top=5'

# Search with pagination
curl -X GET "https://mcp-search-app.azurecontainerapps.io/search?query=documents&top=10&skip=20" \
  -H "Authorization: Bearer "
```

### **Response Format**
```json
{
  "value": [
    {
      "id": "doc123",
      "content": "Document content with search terms...",
      "vector": [0.1, 0.2, 0.3, ...],
      "@search.score": 0.85
    }
  ],
  "@odata.count": 42,
  "search_metadata": {
    "query": "machine learning",
    "filters_applied": "search.score() gt 0.7",
    "has_vector_search": true,
    "vector_dimensions": 1536,
    "timestamp": "2024-07-31T12:00:00Z"
  }
}
```

### **Testing MCP Search Service**
Use the provided test script:
```bash
# Test your deployed MCP service
python examples/test_mcp_search.py https://your-mcp-app.azurecontainerapps.io

# Test locally
python examples/test_mcp_search.py http://localhost:50052
```

For detailed documentation, see [docs/MCP_SEARCH_SERVICE.md](docs/MCP_SEARCH_SERVICE.md).

## Configuration

### **Required Environment Variables**
None if ran from .\scripts\deploy-all.ps1

### **Performance & Concurrency Settings**
```bash
# Concurrent processing (tune based on Azure quotas)
CONCURRENT_MESSAGE_PROCESSING=5    # Service Bus message concurrency
CONCURRENT_FILE_PROCESSING=3       # Embedding generation concurrency

# Retry and rate limiting
MAX_RETRIES=3                      # Maximum retry attempts
RETRY_DELAY_SECONDS=2              # Base retry delay
RATE_LIMIT_BASE_WAIT=60           # Default rate limit wait (seconds)
RATE_LIMIT_MAX_WAIT=300           # Maximum rate limit wait (seconds)
```

### **Document Processing Settings**
```bash
# Token and chunking configuration
CHUNK_MAX_TOKENS=4000              # Max tokens per processing chunk
EMBEDDING_MAX_TOKENS=8000          # Max tokens for embeddings (OpenAI limit)
OVERLAP_TOKENS=200                 # Token overlap between chunks
ENCODING_MODEL=cl100k_base         # Tiktoken encoding model

# File processing limits
MAX_FILE_SIZE_MB=100               # Maximum file size in MB
MAX_PAGES_PER_CHUNK=10            # For PDF/DOCX chunking
```

### **API and Model Configuration**
```bash
# Azure OpenAI settings
OPENAI_API_VERSION=2023-05-15      # API version (matches AI Foundry)
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002
EMBEDDING_VECTOR_DIMENSION=1536    # text-embedding-ada-002 dimensions

# Azure Search settings  
SEARCH_API_VERSION=2024-07-01      # Latest search API version

# MCP Search Service settings
MCP_HTTP_PORT=50052                # MCP service port
AUTHENTICATED_TENANT_ID=  # Valid auth token
```

## Monitoring & Observability

### **Health Endpoints**
- **Indexer Service**:
  - Health Check: `GET /health` - Basic service health with configuration
  - Readiness Check: `GET /ready` - Client initialization status
  - Manual Processing: `POST /process` - Test endpoint for debugging
- **MCP Search Service**:
  - Health Check: `GET /health` - Service health and configuration
  - Readiness Check: `GET /ready` - Client initialization status
  - Search API: `GET /search` - Secure search endpoint with token auth

### **Performance Metrics**
The services provide detailed logging for:
- **Processing Times**: Per-file and per-chunk timing (Indexer)
- **Token Statistics**: Token counts and chunk distributions (Indexer)
- **Concurrency Stats**: Success/failure rates for concurrent operations (Indexer)
- **Rate Limit Events**: Automatic backoff and recovery times (Indexer)
- **Search Performance**: Query execution times and result counts (MCP Search)
- **Authentication Events**: Token validation success/failure (MCP Search)
- **API Response Details**: Full request/response logging for debugging (Both)

## Security & Authentication

### **Managed Identity Architecture**
- **User-Assigned Managed Identity**: Single identity across all Azure services
- **RBAC Permissions**: Least privilege access with role-based security
- **Keyless Authentication**: No connection strings or secrets in code
- **Token-Based APIs**: Azure OpenAI custom domain with managed identity tokens

### **Security Features**
- **Network Security**: Virtual network integration and private endpoints support
- **Secret Management**: All sensitive data managed via Azure Key Vault integration
- **Audit Logging**: Comprehensive activity logs for compliance
- **Zero-Trust Architecture**: Identity verification for every service interaction

## Development & Customization

### **Custom Processing Logic**
To extend file processing capabilities:

1. **Add new file types** in `SUPPORTED_*_EXTENSIONS` constants
2. **Implement extraction logic** in `FileProcessor.extract_content_and_pages()`
3. **Add custom chunking strategy** in `TokenAwareChunker` class
4. **Update container image** and redeploy

### **Custom Search Index Schema**
To modify the Azure AI Search index schema:

1. **Edit the index definition** in `index_definiton/index.json`
2. **Add new fields** or modify existing field properties
3. **Update vector dimensions** if using a different embedding model
4. **Re-run infrastructure deployment** to recreate the index

The default schema includes:
- `id` (String, Key) - Unique document identifier
- `content` (String, Searchable) - Document text content
- `vector` (Collection of Singles) - 1536-dimension embeddings for semantic search

### **Performance Tuning**
Based on your Azure quotas and requirements:

```bash
# High-throughput configuration
CONCURRENT_MESSAGE_PROCESSING=10
CONCURRENT_FILE_PROCESSING=5
CHUNK_MAX_TOKENS=2000

# Conservative configuration (lower quotas)
CONCURRENT_MESSAGE_PROCESSING=2
CONCURRENT_FILE_PROCESSING=1
CHUNK_MAX_TOKENS=6000
```

## Troubleshooting

### **Common Issues & Solutions**

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Rate Limiting** | 429 errors, processing delays | Adjust `CONCURRENT_*` settings downward |
| **Memory Issues** | Container restarts, OOM errors | Reduce `CHUNK_MAX_TOKENS` or file size limits |
| **Authentication Failures** | Token errors, 401/403 responses | Verify managed identity RBAC assignments |
| **Processing Stuck** | Messages in queue, no progress | Check indexer container logs for specific errors |
| **Embedding Failures** | Zero vectors in search index | Verify OpenAI custom domain and model deployment |
| **MCP Auth Failures** | 401 Unauthorized from MCP API | Check Bearer token: `` |
| **Search Timeouts** | MCP search API timeouts | Check Azure Search service health and quota limits |

### **Diagnostic Commands**
```bash
# Check deployment status
.\scripts\get-deployment-status.ps1

# Validate infrastructure  
.\scripts\validate-infrastructure.ps1

# View real-time logs
az containerapp logs show --name indexer-app --resource-group <rg-name> --follow
az containerapp logs show --name mcp-search-app --resource-group <rg-name> --follow

# Test MCP Search Service
curl -X GET "https://<mcp-app-url>/search?query=test" \
  -H "Authorization: Bearer "

# Test OpenAI connectivity
curl -X POST "https://<openai-endpoint>/openai/deployments/text-embedding-ada-002/embeddings" \
  -H "Authorization: Bearer $(az account get-access-token --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)" \
  -H "Content-Type: application/json" \
  -d '{"input": "test text"}'
```

## Performance Benchmarks

### **Throughput Metrics** (based on 1KB average file size)
| Configuration | Files/Hour | Peak Concurrent | Memory Usage |
|---------------|------------|-----------------|--------------|
| **Conservative** (2/1) | ~150-200 | 2 messages | ~200MB |
| **Balanced** (5/3) | ~400-600 | 5 messages | ~500MB |  
| **High-Performance** (10/5) | ~800-1200 | 10 messages | ~1GB |

### **Auto-Scaling Behavior**
- **Scale Trigger**: Service Bus queue length > 30 messages
- **Scale Up**: Additional container instances (max 10)
- **Scale Down**: After queue length < 5 for 5+ minutes
- **Cold Start**: ~30-45 seconds for new container instances