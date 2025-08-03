# Indexer App

This service processes files from Azure Blob Storage and indexes them into Azure AI Search with embeddings from Azure OpenAI.

## Features
- Event-driven processing via Azure Service Bus SDK
- Direct HTTP calls to Azure OpenAI and Azure AI Search with token authentication
- Content extraction from various file types (TXT, PDF, DOCX, JSON)
- Intelligent chunking with token-based limits
- Modular architecture with proper separation of concerns

## Dependencies
- Uses shared libraries from `../../shared/`
- Azure Blob Storage integration
- Azure AI Search integration
- Azure OpenAI integration
- Azure Service Bus integration

## Usage
```bash
docker build -t indexer-app .
docker run -p 50051:50051 indexer-app
```

## Configuration
Configure via environment variables for Azure resources
