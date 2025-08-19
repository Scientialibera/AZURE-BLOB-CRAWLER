# Azure Event-Driven File Processing Pipeline

This solution implements a **high-performance, event-driven microservice architecture** on Azure that automatically processes files as they arrive in blob storage. The pipeline uses Azure Blob Storage, Event Grid, Service Bus, Container Apps, Azure OpenAI, and Azure AI Search.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Blob Storage  │───▶│   Event Grid    │───▶│  Service Bus    │
│    (Landing)    │    │  (BlobCreated)  │    │    (Queue)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Azure AI Search│◀───│ Container Apps  │◀───│  KEDA Scaler    │
│  (Vector Index) │    │(Auto-Scaling)   │    │(Queue-Based)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               ▲                       
                               │                       
                      ┌─────────────────┐               
                      │ Azure OpenAI    │               
                      │(Custom Domain)  │               
                      └─────────────────┘               

```

## Key Features

### **High-Performance Processing**
- **KEDA Auto-Scaling**: Automatic container scaling based on Service Bus queue depth (0-3 replicas)
- **Intelligent Lock Management**: Configurable message lock renewal for long-running processing
- **Concurrent Message Processing**: Configurable parallel processing of Service Bus messages (default: 5 concurrent)
- **Concurrent Embedding Generation**: Parallel embedding creation for document chunks (default: 3 concurrent) 
- **Smart Rate Limiting**: Intelligent retry logic with automatic backoff for Azure

### **Intelligent Document Processing**
- **Token-Aware Chunking**: Preserves document structure while respecting token limits
- **Multi-Format Support**: TXT, PDF, DOCX, JSON, MD, CSV files
- **Page-Aware Processing**: Keeps PDF pages and DOCX sections intact when possible
- **Vector Embeddings**: Azure OpenAI integration for semantic search capabilities

### **Enterprise-Grade Reliability**
- **Advanced Retry Logic**: Handles rate limits, transient failures, and API quotas
- **Zero-Downtime Processing**: Event-driven architecture with message persistence
- **Comprehensive Error Handling**: Graceful degradation and detailed logging
- **Managed Identity Authentication**: Secure, keyless authentication throughout

### **Production-Ready Features**
- **KEDA-Based Scaling**: Scales from 0-3 replicas based on queue depth (10 messages per replica)
- **Configurable Lock Renewal**: Automatic message lock extension for long document processing
- **Configurable Scaling**: Tune concurrency based on your Azure quotas
- **Detailed Telemetry**: Comprehensive logging with performance metrics
- **Manual Processing API**: Test endpoint for development and debugging

## Components

1. **Azure Blob Storage**: Landing zone for files to be processed
2. **Azure Event Grid**: Publishes blob creation events
3. **Azure Service Bus**: Reliable message queue for event processing
4. **Azure Container Apps**: Hosts the file processing microservice
5. **Azure Service Bus SDK**: Direct SDK integration for queue message processing
6. **Azure AI Search**: Indexes processed file content with vector embeddings
7. **Azure OpenAI**: Generates embeddings for semantic search capabilities
8. **Azure Container Registry**: Stores container images
9. **MCP Server**: Model Context Protocol server for AI assistant integration

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
   # PowerShell - Deploy infrastructure and indexer
   .\scripts\deploy-all.ps1
   
   # Deploy MCP server for AI assistant integration
   .\scripts\deploy-mcp.ps1
   
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
   # Check container logs
   az containerapp logs show \
     --name <app-name> \
     --resource-group <resource-group>
   
   # Check health endpoint  
   curl https://<app-url>/health
   ```

3. **Verify indexing in Azure AI Search**:
   - Navigate to Azure Portal → Search Service → Search Explorer
   - Query for your document content

4. **Test MCP Server** (for AI assistant integration):
   ```powershell
   # Test search capabilities via MCP server
   $token = az account get-access-token --tenant <tenant-id> --scope https://search.azure.com/.default --query accessToken --output tsv
   
   # Test search tool
   Invoke-RestMethod -Uri "https://mcp-server.<your-domain>.azurecontainerapps.io/messages" -Method Post -ContentType "application/json" -Body '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "perform_search", "arguments": {"search_text": "test", "authorization": "Bearer '$token'"}}}'
   ```

## Configuration

### **Required Environment Variables**
None if ran from .\scripts\deploy-all.ps1

### **Performance & Concurrency Settings**
```bash
# Concurrent processing (tune based on Azure quotas)
CONCURRENT_MESSAGE_PROCESSING=5    # Service Bus message concurrency
CONCURRENT_FILE_PROCESSING=3       # Embedding generation concurrency

# KEDA auto-scaling settings (applied at deployment)
# Queue-based scaling: 0-3 replicas, 10 messages per replica trigger

# Service Bus lock management
SERVICEBUS_LOCK_RENEWAL_ENABLED=true     # Enable automatic lock renewal
SERVICEBUS_LOCK_RENEWAL_INTERVAL=20      # Lock renewal interval (seconds)
SERVICEBUS_LOCK_DURATION=30              # Default lock duration (seconds)
SERVICEBUS_MAX_DELIVERY_COUNT=10         # Max delivery attempts before dead letter

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
```

## Monitoring & Observability

### **Health Endpoints**
- **Health Check**: `GET /health` - Basic service health with configuration
- **Readiness Check**: `GET /ready` - Client initialization status
- **Manual Processing**: `POST /process` - Test endpoint for debugging

### **Performance Metrics**
The service provides detailed logging for:
- **Processing Times**: Per-file and per-chunk timing
- **Token Statistics**: Token counts and chunk distributions  
- **Concurrency Stats**: Success/failure rates for concurrent operations
- **Rate Limit Events**: Automatic backoff and recovery times
- **API Response Details**: Full request/response logging for debugging

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
SERVICEBUS_LOCK_RENEWAL_INTERVAL=15  # More aggressive lock renewal

# Conservative configuration (lower quotas)
CONCURRENT_MESSAGE_PROCESSING=2
CONCURRENT_FILE_PROCESSING=1
CHUNK_MAX_TOKENS=6000
SERVICEBUS_LOCK_RENEWAL_ENABLED=false  # Disable if processing is fast

# Long-running document processing
SERVICEBUS_LOCK_RENEWAL_ENABLED=true
SERVICEBUS_LOCK_RENEWAL_INTERVAL=10   # Frequent renewal
SERVICEBUS_LOCK_DURATION=60           # Longer initial lock
```

## Troubleshooting

### **Common Issues & Solutions**

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Rate Limiting** | 429 errors, processing delays | Adjust `CONCURRENT_*` settings downward |
| **Memory Issues** | Container restarts, OOM errors | Reduce `CHUNK_MAX_TOKENS` or file size limits |
| **Authentication Failures** | Token errors, 401/403 responses | Verify managed identity RBAC assignments |
| **Processing Stuck** | Messages in queue, no progress | Check container logs for specific errors |
| **Embedding Failures** | Zero vectors in search index | Verify OpenAI custom domain and model deployment |
| **Lock Timeout Issues** | Duplicate processing, lock errors | Enable `SERVICEBUS_LOCK_RENEWAL_ENABLED=true` |
| **Scaling Issues** | KEDA not scaling up/down | Check Service Bus queue metrics and KEDA logs |

### **Diagnostic Commands**
```bash
# Check deployment status
.\scripts\get-deployment-status.ps1

# Validate infrastructure  
.\scripts\validate-infrastructure.ps1

# View real-time logs
az containerapp logs show --name <app-name> --resource-group <rg-name> --follow

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
- **Scale Trigger**: Service Bus queue length ≥ 10 messages per replica
- **Scale Up**: Additional container instances (max 3 replicas)
- **Scale Down**: After queue length < 10 for 5+ minutes  
- **Scale to Zero**: When queue is empty for extended period
- **Cold Start**: ~30-45 seconds for new container instances
- **KEDA Polling**: Checks queue depth every 30 seconds