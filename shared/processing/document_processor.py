"""
Document processing and indexing service

This module handles the complete document processing pipeline including
content extraction, chunking, embedding generation, and search index upload.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from azure_clients import create_credential, DirectOpenAIClient, DirectSearchClient, DirectBlobClient
from utils import TokenAwareChunker, retry_logic
from utils.exceptions import BlobNotFoundError, ProcessingSkippedError
from processing.file_extractor import FileExtractor
from config.settings import (
    STORAGE_ACCOUNT_NAME, SEARCH_SERVICE_NAME, OPENAI_SERVICE_NAME, SEARCH_INDEX_NAME,
    BLOB_ENDPOINT_SUFFIX, SEARCH_ENDPOINT_SUFFIX, AZURE_SEARCH_SCOPE, AZURE_COGNITIVE_SCOPE,
    CHUNK_MAX_TOKENS, EMBEDDING_MAX_TOKENS, SUPPORTED_DOCUMENT_EXTENSIONS,
    CONCURRENT_FILE_PROCESSING, EMBEDDING_VECTOR_DIMENSION, OPENAI_EMBEDDING_MODEL,
    SEARCH_ACTION_UPLOAD, DOCUMENT_ID_FIELD, DOCUMENT_CONTENT_FIELD, DOCUMENT_VECTOR_FIELD,
    SEARCH_ACTION_FIELD, MAX_RETRIES, RETRY_DELAY_SECONDS, TOKEN_PRE_WARMING_ENABLED,
    VERBOSE_AUTH_LOGGING, DELETE_BLOB_AFTER_PROCESSING
)

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Handles complete document processing pipeline
    
    This class orchestrates the entire document processing workflow from content
    extraction through embedding generation to search index upload.
    """
    
    def __init__(self):
        """Initialize the document processor"""
        self.credential = create_credential()
        self.blob_client: Optional[DirectBlobClient] = None
        self.search_client: Optional[DirectSearchClient] = None
        self.openai_client: Optional[DirectOpenAIClient] = None
        self.file_extractor: Optional[FileExtractor] = None
        self.chunker = TokenAwareChunker()
        
    async def initialize(self):
        """
        Initialize Azure clients using managed identity
        
        Raises:
            Exception: If client initialization fails
        """
        try:
            logger.info("   Initializing Azure clients with managed identity authentication...")
            
            # Test credential to verify managed identity access
            from config.settings import AZURE_MANAGEMENT_SCOPE
            token = await self.credential.get_token(AZURE_MANAGEMENT_SCOPE)
            logger.info("   User-Assigned Managed Identity authentication verified successfully")
            
            # Initialize Blob Storage client with managed identity
            if STORAGE_ACCOUNT_NAME:
                blob_service_url = f"https://{STORAGE_ACCOUNT_NAME}{BLOB_ENDPOINT_SUFFIX}"
                self.blob_client = DirectBlobClient(
                    account_url=blob_service_url,
                    credential=self.credential
                )
                logger.info(f"   INITIALIZED Blob Storage client for {STORAGE_ACCOUNT_NAME}")
                
                # Initialize file extractor
                self.file_extractor = FileExtractor(self.blob_client)
            
            # Initialize Search client with direct HTTP calls
            if SEARCH_SERVICE_NAME:
                self.search_client = DirectSearchClient(
                    endpoint=f"https://{SEARCH_SERVICE_NAME}{SEARCH_ENDPOINT_SUFFIX}",
                    credential=self.credential,
                    scope=AZURE_SEARCH_SCOPE,
                    index_name=SEARCH_INDEX_NAME
                )
                logger.info(f"   INITIALIZED Search client for {SEARCH_SERVICE_NAME}")
            
            # Initialize OpenAI client with direct HTTP calls
            if OPENAI_SERVICE_NAME:
                # Use the service-specific endpoint with custom subdomain for token authentication
                openai_endpoint = f"https://{OPENAI_SERVICE_NAME}.openai.azure.com"
                
                self.openai_client = DirectOpenAIClient(
                    endpoint=openai_endpoint,
                    credential=self.credential,
                    scope=AZURE_COGNITIVE_SCOPE
                )
                logger.info(f"   INITIALIZED OpenAI client with endpoint {openai_endpoint}")
            
            logger.info("   All Azure clients initialized successfully")
            
            # Pre-warm all client tokens for faster processing (if enabled)
            if TOKEN_PRE_WARMING_ENABLED:
                await self.pre_warm_all_tokens()
            else:
                logger.info("   Token pre-warming disabled - tokens will be acquired on-demand")
                
        except Exception as e:
            logger.error(f"   Failed to initialize clients: {e}")
            raise
    
    async def pre_warm_all_tokens(self):
        """
        Pre-warm tokens for all Azure clients to ensure they're ready for processing
        
        This method acquires tokens for all clients during startup so that
        file processing doesn't have to wait for token acquisition.
        """
        if VERBOSE_AUTH_LOGGING:
            logger.info("   Starting token pre-warming for all Azure clients...")
        
        pre_warming_tasks = []
        
        # Pre-warm blob client token
        if self.blob_client:
            if VERBOSE_AUTH_LOGGING:
                logger.info("   Pre-warming Blob Storage token...")
            pre_warming_tasks.append(
                ("Blob Storage", self.blob_client.pre_warm_token())
            )
        
        # Pre-warm search client token
        if self.search_client:
            if VERBOSE_AUTH_LOGGING:
                logger.info("   Pre-warming Search token...")
            pre_warming_tasks.append(
                ("Azure AI Search", self.search_client.pre_warm_token())
            )
        
        # Pre-warm OpenAI client token
        if self.openai_client:
            if VERBOSE_AUTH_LOGGING:
                logger.info("   Pre-warming OpenAI token...")
            pre_warming_tasks.append(
                ("Azure OpenAI", self.openai_client.pre_warm_token())
            )
        
        # Execute all pre-warming tasks concurrently
        if pre_warming_tasks:
            task_names = [name for name, _ in pre_warming_tasks]
            tasks = [task for _, task in pre_warming_tasks]
            
            if VERBOSE_AUTH_LOGGING:
                logger.info(f"   Executing concurrent token pre-warming for: {', '.join(task_names)}")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log results
            successful = 0
            for i, (name, result) in enumerate(zip(task_names, results)):
                if isinstance(result, Exception):
                    logger.warning(f"   Token pre-warming failed for {name}: {result}")
                elif result:
                    if VERBOSE_AUTH_LOGGING:
                        logger.info(f"   Token pre-warming successful for {name}")
                    successful += 1
                else:
                    logger.warning(f"   Token pre-warming returned False for {name}")
            
            if VERBOSE_AUTH_LOGGING:
                logger.info(f"   Token pre-warming complete: {successful}/{len(task_names)} successful")
        else:
            if VERBOSE_AUTH_LOGGING:
                logger.info("   No clients available for token pre-warming")
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def generate_embeddings(self, text: str) -> List[float]:
        """
        Generate embeddings for text using Azure OpenAI
        
        Args:
            text: Text to generate embeddings for
            
        Returns:
            List[float]: Vector embeddings
            
        Raises:
            ValueError: If OpenAI client not initialized
        """
        try:
            if not self.openai_client:
                raise ValueError("OpenAI client not initialized")
            
            # Ensure text doesn't exceed embedding token limit
            token_count = self.chunker.count_tokens(text)
            if token_count > EMBEDDING_MAX_TOKENS:
                logger.warning(f"Text ({token_count} tokens) exceeds embedding limit ({EMBEDDING_MAX_TOKENS}), truncating")
                # Use tiktoken to truncate properly
                tokens = self.chunker.tokenizer.encode(text)
                truncated_tokens = tokens[:EMBEDDING_MAX_TOKENS]
                text = self.chunker.tokenizer.decode(truncated_tokens)
            
            logger.info('Sending Chunk to embedding model')
            # Generate embeddings using direct HTTP call
            return await self.openai_client.create_embeddings(text, OPENAI_EMBEDDING_MODEL)
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings, using zero vector fallback: {e}")
            # Return zero vector if embedding fails after all retries
            return [0.0] * EMBEDDING_VECTOR_DIMENSION  # text-embedding-ada-002 produces 1536-dimensional vectors
    
    async def index_document_chunks(self, base_document: Dict[str, Any], chunks: List[str]) -> None:
        """
        Index document chunks in Azure AI Search with concurrent embedding generation
        
        Args:
            base_document: Base document metadata
            chunks: List of text chunks to index
            
        Raises:
            ValueError: If search client not initialized
            Exception: If indexing fails
        """
        try:
            if not self.search_client:
                raise ValueError("Search client not initialized")
            
            logger.info(f"Generating embeddings for {len(chunks)} chunks concurrently...")
            
            # Create semaphore for concurrent embedding generation
            embedding_semaphore = asyncio.Semaphore(CONCURRENT_FILE_PROCESSING)
            
            async def generate_chunk_embedding_with_semaphore(chunk: str, chunk_index: int):
                async with embedding_semaphore:
                    embedding = await self.generate_embeddings(chunk)
                    return chunk_index, chunk, embedding
            
            # Generate embeddings for all chunks concurrently
            logger.info(f"Waiting for concurrent embedding generation")
            embedding_tasks = [
                generate_chunk_embedding_with_semaphore(chunk, i) 
                for i, chunk in enumerate(chunks)
            ]
            
            embedding_results = await asyncio.gather(*embedding_tasks, return_exceptions=True)
            
            # Prepare documents for indexing
            documents_to_index = []
            successful_embeddings = 0
            
            for result in embedding_results:
                if isinstance(result, Exception):
                    logger.error(f"Embedding generation failed: {result}")
                    continue
                
                chunk_index, chunk, chunk_embedding = result
                successful_embeddings += 1
                
                # Create document for this chunk with only 3 fields: id, content, vector
                chunk_doc = {
                    SEARCH_ACTION_FIELD: SEARCH_ACTION_UPLOAD,  # Required for search API
                    DOCUMENT_ID_FIELD: f"{base_document['id']}_chunk_{chunk_index}",
                    DOCUMENT_CONTENT_FIELD: chunk,
                    DOCUMENT_VECTOR_FIELD: chunk_embedding
                }
                
                documents_to_index.append(chunk_doc)
            
            logger.info(f"Generated {successful_embeddings}/{len(chunks)} embeddings successfully")
            
            if not documents_to_index:
                raise Exception("No documents to index - all embedding generations failed")
            
            # Batch upload documents using direct HTTP call
            success = await self.search_client.upload_documents(documents_to_index)
            
            if success:
                logger.info(f"Successfully indexed {len(documents_to_index)} chunks for document {base_document['blob_name']}")
            else:
                raise Exception("Failed to upload documents to search index")
            
        except Exception as e:
            logger.error(f"Failed to index document chunks: {e}")
            raise
    
    async def process_file(self, blob_name: str, container_name: str) -> None:
        """
        Process a single file with intelligent chunking
        
        Args:
            blob_name: Name of the blob to process
            container_name: Container containing the blob
            
        Raises:
            ValueError: If file extractor not initialized
            Exception: If file processing fails
        """
        try:
            logger.info(f"Processing file: {blob_name} from container: {container_name}")
            start_time = datetime.utcnow()
            
            if not self.file_extractor:
                raise ValueError("File extractor not initialized")
            
            # Extract content and pages
            full_content, pages = await self.file_extractor.extract_content_and_pages(blob_name, container_name)
            
            if not full_content.strip():
                logger.warning(f"No content extracted from {blob_name}")
                return
            
            # Determine chunking strategy based on file type
            file_extension = blob_name.lower().split('.')[-1] if '.' in blob_name else ''
            
            if file_extension in SUPPORTED_DOCUMENT_EXTENSIONS and len(pages) > 1:
                # Use page-aware chunking for documents
                logger.info(f"Using page-aware chunking for {blob_name} ({len(pages)} pages)")
                chunks = self.chunker.chunk_pages(pages, CHUNK_MAX_TOKENS)
            else:
                # Use text chunking for other files
                logger.info(f"Using text chunking for {blob_name}")
                chunks = self.chunker.chunk_text(full_content, CHUNK_MAX_TOKENS)
            
            logger.info(f"Created {len(chunks)} chunks for {blob_name}")
            
            # Log chunk statistics
            total_tokens = sum(self.chunker.count_tokens(chunk) for chunk in chunks)
            avg_tokens = total_tokens / len(chunks) if chunks else 0
            logger.info(f"Token statistics - Total: {total_tokens}, Average per chunk: {avg_tokens:.0f}")
            
            # Create base document metadata
            base_document = {
                'id': blob_name.replace('/', '_').replace('.', '_'),
                'blob_name': blob_name,
                'container_name': container_name,
                'processed_date': start_time.isoformat(),
                'file_size': len(full_content.encode('utf-8')),
                'file_type': file_extension or 'unknown',
                'total_tokens': total_tokens,
                'chunk_count': len(chunks)
            }
            
            # Index document chunks (now asynchronous)
            await self.index_document_chunks(base_document, chunks)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Successfully processed file: {blob_name} in {processing_time:.2f}s")
            
            # Delete the blob after successful processing (if enabled)
            if DELETE_BLOB_AFTER_PROCESSING:
                try:
                    if self.blob_client:
                        delete_success = await self.blob_client.delete_blob(blob_name, container_name)
                        if delete_success:
                            logger.info(f"Successfully deleted blob: {blob_name} after processing")
                        else:
                            logger.warning(f"Failed to delete blob: {blob_name} after processing")
                    else:
                        logger.warning("Blob client not available for deletion")
                except Exception as delete_error:
                    # Log the error but don't fail the processing - the document was successfully indexed
                    logger.error(f"Failed to delete blob {blob_name} after processing: {delete_error}")
                    logger.info(f"Document {blob_name} was successfully processed and indexed, but blob deletion failed")
            else:
                logger.debug(f"Blob deletion disabled - keeping {blob_name} in storage")
            
        except BlobNotFoundError as e:
            logger.warning(f"Blob not found, skipping processing: {e}")
            # Re-raise to let calling code know this should be marked as processed, not failed
            raise
        except ProcessingSkippedError as e:
            logger.info(f"Processing skipped: {e}")
            # Re-raise to let calling code know this should be marked as processed, not failed
            raise
        except Exception as e:
            logger.error(f"Error processing file {blob_name}: {e}")
            raise
