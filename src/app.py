"""
Azure File Processing Microservice - Simplified with Direct HTTP Calls

This microservice processes files from Azure Blob Storage when triggered by Service Bus messages.
It extracts content from files and indexes them in Azure AI Search with intelligent chunking.

Features:
- Event-driven processing via Azure Service Bus SDK
- Direct HTTP calls to Azure OpenAI and Azure AI Search with token authentication
- Content extraction from various file types (TXT, PDF, DOCX, JSON)
- Intelligent chunking with token-based limits
- Simplified error handling and logging
"""

import os
import json
import logging
import asyncio
import io
import re
import threading
import pytz
import requests
import time
import functools
from typing import Optional, Dict, Any, List, Tuple, Callable
from datetime import datetime, timezone, timedelta
from threading import Lock
from inspect import iscoroutinefunction

import tiktoken
import PyPDF2
from docx import Document
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.core.exceptions import AzureError
from aiohttp import web

# ====== CONFIGURATION CONSTANTS ======
# Environment variables
STORAGE_ACCOUNT_NAME = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
SEARCH_SERVICE_NAME = os.getenv('AZURE_SEARCH_SERVICE_NAME')
OPENAI_SERVICE_NAME = os.getenv('AZURE_OPENAI_SERVICE_NAME')
SEARCH_INDEX_NAME = os.getenv('AZURE_SEARCH_INDEX_NAME', 'documents')
SERVICEBUS_NAMESPACE = os.getenv('SERVICEBUS_NAMESPACE')
SERVICEBUS_QUEUE_NAME = os.getenv('SERVICEBUS_QUEUE_NAME', 'indexqueue')

# Token and API configuration
TOKEN_LF = int(os.getenv('TOKEN_LIFETIME_MINUTES', '45'))  # Token lifetime in minutes
OPENAI_API_VERSION = os.getenv('OPENAI_API_VERSION', '2023-05-15')  # Match AI Foundry version
SEARCH_API_VERSION = os.getenv('SEARCH_API_VERSION', '2024-07-01')
OPENAI_EMBEDDING_MODEL = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-ada-002')

# Token limits and chunking configuration
CHUNK_MAX_TOKENS = int(os.getenv('CHUNK_MAX_TOKENS', '4000'))  # Max tokens per chunk for processing
EMBEDDING_MAX_TOKENS = int(os.getenv('EMBEDDING_MAX_TOKENS', '8000'))  # Max tokens for embedding (OpenAI limit)
OVERLAP_TOKENS = int(os.getenv('OVERLAP_TOKENS', '200'))  # Token overlap between chunks
ENCODING_MODEL = os.getenv('ENCODING_MODEL', 'cl100k_base')  # Tiktoken encoding model

# File processing limits
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '100'))  # Maximum file size in MB
MAX_PAGES_PER_CHUNK = int(os.getenv('MAX_PAGES_PER_CHUNK', '10'))  # For PDF/DOCX chunking

# Retry and timeout configuration
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
RETRY_DELAY_SECONDS = int(os.getenv('RETRY_DELAY_SECONDS', '2'))
REQUEST_TIMEOUT_SECONDS = int(os.getenv('REQUEST_TIMEOUT_SECONDS', '60'))

# Rate limit handling configuration
RATE_LIMIT_BASE_WAIT = int(os.getenv('RATE_LIMIT_BASE_WAIT', '60'))  # Base wait time for rate limits
RATE_LIMIT_MAX_WAIT = int(os.getenv('RATE_LIMIT_MAX_WAIT', '300'))  # Maximum wait time for rate limits

# HTTP and networking constants
HTTP_PORT = int(os.getenv('HTTP_PORT', '50051'))  # Server port
HTTP_HOST = os.getenv('HTTP_HOST', '0.0.0.0')  # Server host
HTTP_LOCALHOST = os.getenv('HTTP_LOCALHOST', 'localhost')  # Localhost for logging

# Azure service endpoints and scopes
AZURE_MANAGEMENT_SCOPE = "https://management.azure.com/.default"
AZURE_SEARCH_SCOPE = "https://search.azure.com/.default"
AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
BLOB_ENDPOINT_SUFFIX = ".blob.core.windows.net"
SEARCH_ENDPOINT_SUFFIX = ".search.windows.net"
SERVICEBUS_ENDPOINT_SUFFIX = ".servicebus.windows.net"

# OpenAI service endpoint configuration
OPENAI_ENDPOINT_BASE = os.getenv('OPENAI_ENDPOINT_BASE', f'https://{OPENAI_SERVICE_NAME}.openai.azure.com' if OPENAI_SERVICE_NAME else 'https://eastus2.api.cognitive.microsoft.com')

# Embedding model configuration
EMBEDDING_VECTOR_DIMENSION = int(os.getenv('EMBEDDING_VECTOR_DIMENSION', '1536'))  # text-embedding-ada-002 dimensions
EMBEDDING_FALLBACK_TOKEN_RATIO = int(os.getenv('EMBEDDING_FALLBACK_TOKEN_RATIO', '4'))  # 1 token ≈ 4 characters

# Service Bus configuration
SERVICEBUS_MAX_MESSAGES = int(os.getenv('SERVICEBUS_MAX_MESSAGES', '10'))  # Max messages per batch
SERVICEBUS_WAIT_TIME = int(os.getenv('SERVICEBUS_WAIT_TIME', '5'))  # Wait time in seconds

# Concurrent processing configuration
CONCURRENT_MESSAGE_PROCESSING = int(os.getenv('CONCURRENT_MESSAGE_PROCESSING', '5'))  # Number of concurrent message processing tasks
CONCURRENT_FILE_PROCESSING = int(os.getenv('CONCURRENT_FILE_PROCESSING', '3'))  # Number of concurrent file processing operations

# File processing constants
SUPPORTED_TEXT_EXTENSIONS = ['txt', 'md', 'csv']
SUPPORTED_STRUCTURED_EXTENSIONS = ['json']
SUPPORTED_DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'doc']
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_TEXT_EXTENSIONS + SUPPORTED_STRUCTURED_EXTENSIONS + SUPPORTED_DOCUMENT_EXTENSIONS

# Document processing constants
PARAGRAPHS_PER_PAGE = int(os.getenv('PARAGRAPHS_PER_PAGE', '20'))  # Artificial page breaks for DOCX
PAGE_PREFIX = "--- Page "
SECTION_PREFIX = "--- Section "
PAGE_SUFFIX = " ---"

# Text encoding constants
TEXT_ENCODING = 'utf-8'
TEXT_ENCODING_ERRORS = 'ignore'
TIKTOKEN_FALLBACK_MODEL = 'cl100k_base'

# HTTP constants
HTTP_CONTENT_TYPE_JSON = 'application/json'
HTTP_AUTH_BEARER_PREFIX = 'Bearer'
HTTP_SUCCESS_CODES = [200, 201]

# Search API constants
SEARCH_ACTION_UPLOAD = 'upload'
SEARCH_DOCS_INDEX_PATH = '/indexes/{}/docs/index'
OPENAI_EMBEDDINGS_PATH = '/openai/deployments/{}/embeddings'

# Document field names
DOCUMENT_ID_FIELD = 'id'
DOCUMENT_CONTENT_FIELD = 'content'
DOCUMENT_VECTOR_FIELD = 'vector'
SEARCH_ACTION_FIELD = '@search.action'

# Logging constants
TOKEN_PREVIEW_LENGTH = int(os.getenv('TOKEN_PREVIEW_LENGTH', '20'))  # Length of token preview in logs
VECTOR_DISPLAY_TEXT = "[Vector with {} dimensions]"

# Processing sleep intervals
MAIN_LOOP_SLEEP_SECONDS = int(os.getenv('MAIN_LOOP_SLEEP_SECONDS', '3600'))  # 1 hour
ERROR_RETRY_SLEEP_SECONDS = int(os.getenv('ERROR_RETRY_SLEEP_SECONDS', '5'))  # Error retry delay

# Timezone configuration
DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'US/Eastern')  # For logging timestamps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _is_rate_limit_error(error: Exception) -> bool:
    """Check if the error is a rate limit error."""
    error_str = str(error).lower()
    error_codes = ['429', 'rate limit', 'quota exceeded', 'throttled', 'too many requests']
    
    # Check for Azure-specific rate limit indicators
    if hasattr(error, 'response') and error.response:
        status_code = getattr(error.response, 'status_code', None)
        if status_code == 429:
            return True
        
        # Check response text for rate limit indicators
        response_text = getattr(error.response, 'text', '')
        if callable(response_text):
            response_text = response_text()
        if any(code in str(response_text).lower() for code in error_codes):
            return True
    
    # Check error message for rate limit indicators
    return any(code in error_str for code in error_codes)


def _get_wait_time_from_error(error: Exception) -> int:
    """Extract wait time from rate limit error or return default."""
    try:
        # Check for Retry-After header
        if hasattr(error, 'response') and error.response:
            headers = getattr(error.response, 'headers', {})
            if 'retry-after' in headers:
                retry_after = headers['retry-after']
                return min(int(retry_after), RATE_LIMIT_MAX_WAIT)
            elif 'x-ratelimit-reset' in headers:
                # Some APIs use x-ratelimit-reset
                reset_time = int(headers['x-ratelimit-reset'])
                current_time = int(time.time())
                wait_time = max(reset_time - current_time, 0)
                return min(wait_time, RATE_LIMIT_MAX_WAIT)
        
        # Check error message for wait time hints
        error_str = str(error).lower()
        import re
        wait_pattern = r'retry after (\d+) seconds?'
        match = re.search(wait_pattern, error_str)
        if match:
            return min(int(match.group(1)), RATE_LIMIT_MAX_WAIT)
        
    except (ValueError, AttributeError):
        pass
    
    # Return default wait time
    return RATE_LIMIT_BASE_WAIT


def retry_logic(max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY_SECONDS) -> Callable:
    """Retry decorator for sync and async functions with rate limit handling."""
    
    def decorator(func: Callable) -> Callable:
        if iscoroutinefunction(func):
            
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                attempt = 0
                while attempt < max_retries:
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        if _is_rate_limit_error(e):
                            wait_time = _get_wait_time_from_error(e)
                            logger.warning(
                                "Rate limit hit in %s. Waiting %d seconds before retry.",
                                func.__name__, wait_time
                            )
                            await asyncio.sleep(wait_time)
                            # Do not increment the attempt counter for rate limit errors
                            continue
                        else:
                            attempt += 1
                            logger.warning(
                                "Attempt %d/%d failed in %s: %s", 
                                attempt, max_retries, func.__name__, e
                            )
                            if attempt < max_retries:
                                await asyncio.sleep(delay)
                            else:
                                logger.error(
                                    "All %d attempts failed in %s. Raising exception.",
                                    max_retries, func.__name__
                                )
                                raise
                raise RuntimeError(f"Async retry logic exhausted in {func.__name__}")
            
            return async_wrapper
        
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                attempt = 0
                while attempt < max_retries:
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if _is_rate_limit_error(e):
                            wait_time = _get_wait_time_from_error(e)
                            logger.warning(
                                "Rate limit hit in %s. Waiting %d seconds before retry.",
                                func.__name__, wait_time
                            )
                            time.sleep(wait_time)
                            # Do not increment the attempt counter for rate limit errors
                            continue
                        else:
                            attempt += 1
                            logger.warning(
                                "Attempt %d/%d failed in %s: %s", 
                                attempt, max_retries, func.__name__, e
                            )
                            if attempt < max_retries:
                                time.sleep(delay)
                            else:
                                logger.error(
                                    "All %d attempts failed in %s. Raising exception.",
                                    max_retries, func.__name__
                                )
                                raise
                raise RuntimeError(f"Sync retry logic exhausted in {func.__name__}")
            
            return sync_wrapper
    
    return decorator


async def get_token_async(credential, scope):
    """
    Get Azure access token using DefaultAzureCredential
    """
    try:
        logger.info(f"   Requesting token for scope: {scope}")
        token = await credential.get_token(scope)
        logger.info(f"   Token acquired successfully - Expires: {datetime.fromtimestamp(token.expires_on, tz=timezone.utc)}")
        logger.info(f"   Token preview: {token.token[:TOKEN_PREVIEW_LENGTH]}...")
        return token.token
    except Exception as e:
        logger.error(f"   Failed to get token for scope {scope}: {e}")
        return None


class AzureClientBase:
    """
    Base class for managing Azure token-based authentication with thread-safe token refresh.
    """
    def __init__(self, credential, scope):
        self.credential = credential
        self.scope = scope
        self.token = None
        self.token_expiry = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = Lock()  # Thread lock to prevent concurrent token refresh
 
    async def _refresh_token(self):
        """
        Refresh the token if it has expired or does not exist.
        Thread-safe to handle concurrent requests.
        """
        now = datetime.now(timezone.utc)
        thread_id = threading.get_ident()
        now_est = now.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
        logger.info(f"[Thread {thread_id}] checking token at {now_est}")

        if self.token and now < self.token_expiry:
            token_expiry_est = self.token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
            logger.info(f"[Thread {thread_id}] Reusing existing Azure token. Valid until {token_expiry_est.isoformat()}.")
            return  # Token is still valid; no need to refresh

        with self._lock:
            now = datetime.now(timezone.utc)
            if self.token and now < self.token_expiry:
                token_expiry_est = self.token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                logger.info(f"[Thread {thread_id}] Token was refreshed by another thread. Reusing existing token. Valid until {token_expiry_est.isoformat()}.")
                return

            logger.info(f"[Thread {thread_id}] Refreshing Azure token.")
            self.token = await get_token_async(self.credential, self.scope)
            if not self.token:
                raise Exception("Failed to acquire a new token.")
            self.token_expiry = now + timedelta(minutes=TOKEN_LF)  # Adjust based on token TTL
            token_expiry_est = self.token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
            logger.info(f"[Thread {thread_id}] New token acquired. Valid until {token_expiry_est.isoformat()}.")
 
 
    async def _get_headers(self):
        """
        Prepare headers with the current token.
        """
        await self._refresh_token()
        return {"Content-Type": HTTP_CONTENT_TYPE_JSON, "Authorization": f"{HTTP_AUTH_BEARER_PREFIX} {self.token}"}


class DirectOpenAIClient(AzureClientBase):
    """
    Direct HTTP client for Azure OpenAI API
    """
    def __init__(self, endpoint, credential, scope, api_version=OPENAI_API_VERSION):
        super().__init__(credential, scope)
        self.endpoint = endpoint.rstrip('/')
        self.api_version = api_version
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def create_embeddings(self, text: str, model: str = OPENAI_EMBEDDING_MODEL) -> List[float]:
        """
        Create embeddings using direct HTTP call
        """
        url = f"{self.endpoint}/openai/deployments/{model}/embeddings?api-version={self.api_version}"
        headers = await self._get_headers()
        
        payload = {
            "input": text,
            "model": model
        }
        
        # Log detailed information about the request
        logger.info(f"   START OPENAI Embeddings Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Model: {model}")
        logger.info(f"   Text length: {len(text)} chars")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   OpenAI Response - Status: {response.status_code}")
        logger.info(f"   Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.error(f"   OpenAI API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        embedding = result['data'][0]['embedding']
        logger.info(f"   OpenAI Embeddings successful - Vector dimension: {len(embedding)}")
        return embedding


class DirectSearchClient(AzureClientBase):
    """
    Direct HTTP client for Azure AI Search API
    """
    def __init__(self, endpoint, credential, scope, index_name, api_version=SEARCH_API_VERSION):
        super().__init__(credential, scope)
        self.endpoint = endpoint.rstrip('/')
        self.index_name = index_name
        self.api_version = api_version
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def upload_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Upload documents using direct HTTP call
        """
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={self.api_version}"
        headers = await self._get_headers()
        
        payload = {
            "value": documents
        }
        
        # Log detailed information about the request
        logger.info(f"   START SEARCH Index Upload Request:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Index: {self.index_name}")
        logger.info(f"   Document count: {len(documents)}")
        logger.info(f"   Authorization header: {HTTP_AUTH_BEARER_PREFIX} {self.token}..." if self.token else "   No token")
        
        # Log sample document structure (first document only)
        if documents:
            sample_doc = documents[0].copy()
            if 'vector' in sample_doc:
                vector_dim = len(sample_doc['vector']) if sample_doc['vector'] else 0
                sample_doc['vector'] = VECTOR_DISPLAY_TEXT.format(vector_dim)
            logger.info(f"   Sample document: {sample_doc['id']}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details
        logger.info(f"   Search Response - Status: {response.status_code}")
        logger.info(f"   Response headers: {dict(response.headers)}")
        
        if response.status_code not in HTTP_SUCCESS_CODES:
            logger.error(f"   Search API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"   Search Upload successful - Response: {result}")
        logger.info(f"Successfully uploaded {len(documents)} documents to search index")
        return True


class TokenAwareChunker:
    """Handles intelligent text chunking with token limits"""
    
    def __init__(self, encoding_model: str = ENCODING_MODEL):
        """Initialize tokenizer"""
        try:
            self.tokenizer = tiktoken.get_encoding(encoding_model)
        except Exception as e:
            logger.warning(f"Failed to load tokenizer {encoding_model}, using fallback: {e}")
            self.tokenizer = tiktoken.get_encoding(TIKTOKEN_FALLBACK_MODEL)
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        try:
            return len(self.tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Token counting failed, using character estimation: {e}")
            return len(text) // EMBEDDING_FALLBACK_TOKEN_RATIO  # Rough estimation: 1 token ≈ 4 characters
    
    def chunk_text(self, text: str, max_tokens: int = CHUNK_MAX_TOKENS, 
                  overlap_tokens: int = OVERLAP_TOKENS) -> List[str]:
        """
        Chunk text intelligently without breaking sentences
        """
        if not text.strip():
            return []
        
        # If text is within limit, return as single chunk
        if self.count_tokens(text) <= max_tokens:
            return [text]
        
        chunks = []
        sentences = self._split_into_sentences(text)
        
        current_chunk = ""
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            # If single sentence exceeds max tokens, we need to split it
            if sentence_tokens > max_tokens:
                # Add current chunk if not empty
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_tokens = 0
                
                # Split the long sentence by words or characters
                sentence_chunks = self._split_long_sentence(sentence, max_tokens)
                chunks.extend(sentence_chunks[:-1])  # Add all but last
                
                # Start new chunk with last piece
                current_chunk = sentence_chunks[-1] if sentence_chunks else ""
                current_tokens = self.count_tokens(current_chunk)
            
            # If adding this sentence would exceed limit, finalize current chunk
            elif current_tokens + sentence_tokens > max_tokens:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # Handle overlap
                overlap_text = self._get_overlap_text(current_chunk, overlap_tokens)
                current_chunk = overlap_text + " " + sentence
                current_tokens = self.count_tokens(current_chunk)
            else:
                # Add sentence to current chunk
                current_chunk += " " + sentence if current_chunk else sentence
                current_tokens += sentence_tokens
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def chunk_pages(self, pages: List[str], max_tokens: int = CHUNK_MAX_TOKENS) -> List[str]:
        """
        Chunk pages keeping page boundaries intact when possible
        For PDF and DOCX files - don't separate pages unless necessary
        """
        if not pages:
            return []
        
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for page in pages:
            page_tokens = self.count_tokens(page)
            
            # If adding this page would exceed limit, finalize current chunk
            if current_chunk and current_tokens + page_tokens > max_tokens:
                chunks.append(current_chunk.strip())
                current_chunk = page
                current_tokens = page_tokens
            elif not current_chunk:
                # First page
                current_chunk = page
                current_tokens = page_tokens
            else:
                # Add page to current chunk
                current_chunk += "\n\n" + page
                current_tokens += page_tokens
            
            # If single page exceeds max tokens, chunk it
            if page_tokens > max_tokens:
                if current_chunk != page:  # Already added to current chunk
                    chunks.append(current_chunk.replace(page, "").strip())
                
                # Chunk the oversized page
                page_chunks = self.chunk_text(page, max_tokens)
                chunks.extend(page_chunks[:-1])  # Add all but last
                current_chunk = page_chunks[-1] if page_chunks else ""
                current_tokens = self.count_tokens(current_chunk)
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using regex"""
        # Improved sentence splitting that handles common abbreviations
        sentence_endings = r'[.!?]+(?:\s+|$)'
        sentences = re.split(sentence_endings, text)
        
        # Clean up and filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
    
    def _split_long_sentence(self, sentence: str, max_tokens: int) -> List[str]:
        """Split a sentence that's too long by words"""
        words = sentence.split()
        chunks = []
        current_chunk = ""
        
        for word in words:
            test_chunk = current_chunk + " " + word if current_chunk else word
            if self.count_tokens(test_chunk) > max_tokens:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = word
                else:
                    # Single word exceeds limit - split by characters
                    chunks.extend(self._split_by_characters(word, max_tokens))
                    current_chunk = ""
            else:
                current_chunk = test_chunk
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _split_by_characters(self, text: str, max_tokens: int) -> List[str]:
        """Split text by characters when even words are too long"""
        chunks = []
        chars_per_token = EMBEDDING_FALLBACK_TOKEN_RATIO  # Rough estimation
        max_chars = max_tokens * chars_per_token
        
        for i in range(0, len(text), max_chars):
            chunks.append(text[i:i + max_chars])
        
        return chunks
    
    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """Get the last part of text for overlap"""
        if overlap_tokens <= 0:
            return ""
        
        words = text.split()
        overlap_text = ""
        
        # Work backwards from the end
        for i in range(len(words) - 1, -1, -1):
            test_text = " ".join(words[i:]) if overlap_text == "" else " ".join(words[i:])
            if self.count_tokens(test_text) > overlap_tokens:
                break
            overlap_text = test_text
        
        return overlap_text


class FileProcessor:
    """Handles file processing operations with simplified HTTP clients"""
    
    def __init__(self):
        # Use user-assigned managed identity with client ID from environment variable
        user_assigned_client_id = os.getenv("AZURE_CLIENT_ID")
        
        logger.info(f"Using DefaultAzureCredential with client ID: {user_assigned_client_id}")
        self.credential = DefaultAzureCredential(
            managed_identity_client_id=user_assigned_client_id   # optional
        )
        self.blob_client: Optional[BlobServiceClient] = None
        self.search_client: Optional[DirectSearchClient] = None
        self.openai_client: Optional[DirectOpenAIClient] = None
        self.servicebus_client: Optional[ServiceBusClient] = None
        self.servicebus_receiver = None
        self.chunker = TokenAwareChunker()
        self._processing = False
        
    async def initialize(self):
        """Initialize Azure clients using direct HTTP calls and managed identity for blob/servicebus"""
        try:
            logger.info("   Initializing Azure clients with HTTP authentication...")
            logger.info("   Using user-assigned managed identity with pre-configured RBAC permissions")
            
            # Test credential to verify managed identity access
            token = await self.credential.get_token(AZURE_MANAGEMENT_SCOPE)
            logger.info("   User-Assigned Managed Identity authentication verified successfully")
            
            # Initialize Blob Storage client with managed identity (async)
            if STORAGE_ACCOUNT_NAME:
                blob_service_url = f"https://{STORAGE_ACCOUNT_NAME}{BLOB_ENDPOINT_SUFFIX}"
                self.blob_client = BlobServiceClient(
                    account_url=blob_service_url,
                    credential=self.credential
                )
                logger.info(f"   INITIALIZED Blob Storage client for {STORAGE_ACCOUNT_NAME} with User-Assigned Managed Identity")
            
            # Initialize Search client with direct HTTP calls
            if SEARCH_SERVICE_NAME:
                self.search_client = DirectSearchClient(
                    endpoint=f"https://{SEARCH_SERVICE_NAME}{SEARCH_ENDPOINT_SUFFIX}",
                    credential=self.credential,
                    scope=AZURE_SEARCH_SCOPE,
                    index_name=SEARCH_INDEX_NAME
                )
                logger.info(f"   INITIALIZED Search client for {SEARCH_SERVICE_NAME} with direct HTTP calls")
            
            # Initialize Service Bus client with managed identity (async)
            if SERVICEBUS_NAMESPACE:
                self.servicebus_client = ServiceBusClient(
                    fully_qualified_namespace=f"{SERVICEBUS_NAMESPACE}{SERVICEBUS_ENDPOINT_SUFFIX}",
                    credential=self.credential
                )
                
                # Create receiver for the queue
                self.servicebus_receiver = self.servicebus_client.get_queue_receiver(
                    queue_name=SERVICEBUS_QUEUE_NAME,
                    max_wait_time=SERVICEBUS_WAIT_TIME
                )
                logger.info(f"   INITIALIZED Service Bus client for {SERVICEBUS_NAMESPACE} with User-Assigned Managed Identity")
            
            # Initialize OpenAI client with direct HTTP calls
            if OPENAI_SERVICE_NAME:
                # Use the service-specific endpoint with custom subdomain for token authentication
                openai_endpoint = f"https://{OPENAI_SERVICE_NAME}.openai.azure.com"
                
                self.openai_client = DirectOpenAIClient(
                    endpoint=openai_endpoint,
                    credential=self.credential,
                    scope=AZURE_COGNITIVE_SCOPE,
                    api_version=OPENAI_API_VERSION
                )
                logger.info(f"   INITIALIZED OpenAI client with service-specific endpoint {openai_endpoint}")
            
            logger.info("   All Azure clients initialized successfully with simplified authentication")
            logger.info("   Using RBAC permissions assigned during infrastructure deployment")
                
        except Exception as e:
            logger.error(f"   Failed to initialize clients: {e}")
            raise
    
    async def extract_content_and_pages(self, blob_name: str, container_name: str) -> Tuple[str, List[str]]:
        """
        Extract content and pages from blob based on file type
        Returns: (full_content, pages_list)
        """
        try:
            if not self.blob_client:
                raise ValueError("Blob client not initialized")
                
            blob_client = self.blob_client.get_blob_client(
                container=container_name, 
                blob=blob_name
            )
            
            # Check file size
            blob_properties = await blob_client.get_blob_properties()
            file_size_mb = blob_properties.size / (1024 * 1024)
            
            if file_size_mb > MAX_FILE_SIZE_MB:
                logger.warning(f"File {blob_name} ({file_size_mb:.2f}MB) exceeds size limit ({MAX_FILE_SIZE_MB}MB)")
                return f"File too large: {blob_name} ({file_size_mb:.2f}MB)", []
            
            # Download blob content
            blob_data = await blob_client.download_blob()
            content = await blob_data.readall()
            
            file_extension = blob_name.lower().split('.')[-1] if '.' in blob_name else ''
            
            if file_extension in SUPPORTED_TEXT_EXTENSIONS:
                text_content = content.decode(TEXT_ENCODING, errors=TEXT_ENCODING_ERRORS)
                return text_content, [text_content]  # Single page for text files
            
            elif file_extension in SUPPORTED_STRUCTURED_EXTENSIONS:
                try:
                    json_data = json.loads(content.decode(TEXT_ENCODING))
                    text_content = self._extract_text_from_json(json_data)
                    return text_content, [text_content]
                except json.JSONDecodeError:
                    text_content = content.decode(TEXT_ENCODING, errors=TEXT_ENCODING_ERRORS)
                    return text_content, [text_content]
            
            elif file_extension in SUPPORTED_DOCUMENT_EXTENSIONS:
                if file_extension == 'pdf':
                    return await self._extract_pdf_content(content)
                elif file_extension in ['docx', 'doc']:
                    return await self._extract_docx_content(content)
            
            else:
                # For other file types, return metadata
                content_text = f"Binary file: {blob_name} (Size: {file_size_mb:.2f}MB, Type: {file_extension})"
                return content_text, [content_text]
                
        except Exception as e:
            logger.error(f"Failed to extract content from {blob_name}: {e}")
            raise
    
    async def _extract_pdf_content(self, content: bytes) -> Tuple[str, List[str]]:
        """Extract content from PDF, preserving page structure"""
        try:
            pdf_file = io.BytesIO(content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            pages = []
            full_content = ""
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        page_content = f"{PAGE_PREFIX}{page_num + 1}{PAGE_SUFFIX}\n{page_text.strip()}"
                        pages.append(page_content)
                        full_content += page_content + "\n\n"
                except Exception as e:
                    logger.warning(f"Failed to extract text from PDF page {page_num + 1}: {e}")
                    continue
            
            if not pages:
                return "No readable text found in PDF", []
            
            return full_content.strip(), pages
            
        except Exception as e:
            logger.error(f"Failed to process PDF: {e}")
            return "PDF processing failed", []
    
    async def _extract_docx_content(self, content: bytes) -> Tuple[str, List[str]]:
        """Extract content from DOCX, preserving paragraph structure"""
        try:
            docx_file = io.BytesIO(content)
            doc = Document(docx_file)
            
            pages = []
            current_page = ""
            paragraph_count = 0
            paragraphs_per_page = PARAGRAPHS_PER_PAGE  # Arbitrary page break
            
            full_content = ""
            
            for paragraph in doc.paragraphs:
                para_text = paragraph.text.strip()
                if para_text:
                    current_page += para_text + "\n"
                    paragraph_count += 1
                    
                    # Create artificial "pages" based on paragraph count
                    if paragraph_count >= paragraphs_per_page:
                        if current_page.strip():
                            page_content = f"{SECTION_PREFIX}{len(pages) + 1}{PAGE_SUFFIX}\n{current_page.strip()}"
                            pages.append(page_content)
                            full_content += page_content + "\n\n"
                        current_page = ""
                        paragraph_count = 0
            
            # Add remaining content as final page
            if current_page.strip():
                page_content = f"{SECTION_PREFIX}{len(pages) + 1}{PAGE_SUFFIX}\n{current_page.strip()}"
                pages.append(page_content)
                full_content += page_content + "\n\n"
            
            if not pages:
                return "No readable text found in document", []
            
            return full_content.strip(), pages
            
        except Exception as e:
            logger.error(f"Failed to process DOCX: {e}")
            return "DOCX processing failed", []
    
    def _extract_text_from_json(self, data: Any) -> str:
        """Recursively extract text values from JSON"""
        if isinstance(data, dict):
            texts = []
            for key, value in data.items():
                # Include key names for context
                text_value = self._extract_text_from_json(value)
                if text_value:
                    texts.append(f"{key}: {text_value}")
            return '\n'.join(texts)
        elif isinstance(data, list):
            texts = []
            for i, item in enumerate(data):
                text_value = self._extract_text_from_json(item)
                if text_value:
                    texts.append(f"[{i}] {text_value}")
            return '\n'.join(texts)
        elif isinstance(data, str):
            return data
        else:
            return str(data)
    
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def generate_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for text using direct HTTP calls"""
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
            
            # Generate embeddings using direct HTTP call
            return await self.openai_client.create_embeddings(text, OPENAI_EMBEDDING_MODEL)
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings, using zero vector fallback: {e}")
            # Return zero vector if embedding fails after all retries
            return [0.0] * EMBEDDING_VECTOR_DIMENSION  # text-embedding-ada-002 produces 1536-dimensional vectors
    
    async def index_document_chunks(self, base_document: Dict[str, Any], chunks: List[str]) -> None:
        """Index document chunks in Azure AI Search with concurrent embedding generation"""
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
        """Process a single file with intelligent chunking"""
        try:
            logger.info(f"Processing file: {blob_name} from container: {container_name}")
            start_time = datetime.utcnow()
            
            # Extract content and pages
            full_content, pages = await self.extract_content_and_pages(blob_name, container_name)
            
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
            
        except Exception as e:
            logger.error(f"Error processing file {blob_name}: {e}")
            raise

    async def start_service_bus_processing(self):
        """Start processing Service Bus messages with concurrent processing"""
        if not self.servicebus_receiver:
            logger.warning("Service Bus receiver not initialized")
            return
        
        self._processing = True
        logger.info(f"Starting Service Bus message processing with {CONCURRENT_MESSAGE_PROCESSING} concurrent workers...")
        
        try:
            while self._processing:
                try:
                    # Receive messages from Service Bus
                    received_msgs = await self.servicebus_receiver.receive_messages(
                        max_message_count=SERVICEBUS_MAX_MESSAGES, 
                        max_wait_time=SERVICEBUS_WAIT_TIME
                    )
                    
                    if not received_msgs:
                        continue
                    
                    logger.info(f"Received {len(received_msgs)} messages for concurrent processing")
                    
                    # Process messages concurrently using asyncio.gather with semaphore for rate limiting
                    semaphore = asyncio.Semaphore(CONCURRENT_MESSAGE_PROCESSING)
                    
                    async def process_single_message_with_semaphore(msg):
                        async with semaphore:
                            return await self._process_single_message(msg)
                    
                    # Process all messages concurrently
                    tasks = [process_single_message_with_semaphore(msg) for msg in received_msgs]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log results
                    successful = sum(1 for result in results if result is True)
                    failed = len(results) - successful
                    logger.info(f"Batch processing complete - Success: {successful}, Failed: {failed}")
                    
                except Exception as e:
                    logger.error(f"Error receiving messages: {e}")
                    await asyncio.sleep(ERROR_RETRY_SLEEP_SECONDS)  # Wait before retry
                    
        except Exception as e:
            logger.error(f"Service Bus processing error: {e}")
        finally:
            logger.info("Service Bus message processing stopped")

    async def _process_single_message(self, msg) -> bool:
        """Process a single Service Bus message"""
        try:
            # Parse message body
            message_body = str(msg)
            logger.info(f"Processing message: {message_body}")
            
            # Try to parse as JSON
            try:
                message_data = json.loads(message_body)
            except json.JSONDecodeError:
                logger.warning(f"Message not in JSON format: {message_body}")
                await self.servicebus_receiver.complete_message(msg)
                return True
            
            # Extract blob information
            blob_name = None
            container_name = None
            
            # Handle different message formats
            if isinstance(message_data, list) and len(message_data) > 0:
                # Event Grid event format
                event_data = message_data[0]
                if 'data' in event_data and 'url' in event_data['data']:
                    blob_url = event_data['data']['url']
                    # Parse blob URL to extract container and blob name
                    url_parts = blob_url.replace('https://', '').split('/')
                    if len(url_parts) >= 3:
                        container_name = url_parts[1]
                        blob_name = '/'.join(url_parts[2:])
            elif 'blob_name' in message_data and 'container_name' in message_data:
                # Direct format
                blob_name = message_data['blob_name']
                container_name = message_data['container_name']
            elif 'data' in message_data and 'url' in message_data['data']:
                # Single Event Grid event
                blob_url = message_data['data']['url']
                url_parts = blob_url.replace('https://', '').split('/')
                if len(url_parts) >= 3:
                    container_name = url_parts[1]
                    blob_name = '/'.join(url_parts[2:])
            
            if not blob_name or not container_name:
                logger.warning(f"Could not extract blob info from message: {message_data}")
                await self.servicebus_receiver.complete_message(msg)
                return True
            
            # Process the file
            await self.process_file(blob_name, container_name)
            
            # Complete the message
            await self.servicebus_receiver.complete_message(msg)
            logger.info(f"Successfully processed and completed message for {blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Abandon message to allow retry
            try:
                await self.servicebus_receiver.abandon_message(msg)
            except Exception as abandon_error:
                logger.error(f"Failed to abandon message: {abandon_error}")
            return False

    async def stop_service_bus_processing(self):
        """Stop Service Bus message processing"""
        self._processing = False
        if self.servicebus_receiver:
            await self.servicebus_receiver.close()
        if self.servicebus_client:
            await self.servicebus_client.close()


# Global processor instance
processor = FileProcessor()


async def process_blob_event(request):
    """Handle blob creation events from HTTP webhook"""
    try:
        data = await request.json()
        logger.info(f"Received event: {data}")
        
        # Parse event data - can handle both Event Grid and direct calls
        if isinstance(data, list) and len(data) > 0:
            # Event Grid sends array of events
            event_data = data[0]
        else:
            # Direct call
            event_data = data
        
        # Extract blob information from Event Grid event or direct call
        blob_url = ""
        if 'data' in event_data and 'url' in event_data['data']:
            # Event Grid event
            blob_url = event_data['data']['url']
        elif 'blob_name' in event_data and 'container_name' in event_data:
            # Direct call format
            container_name = event_data['container_name']
            blob_name = event_data['blob_name']
        
        if blob_url:
            # Parse blob URL to extract container and blob name
            # URL format: https://storageaccount.blob.core.windows.net/container/blob
            url_parts = blob_url.replace('https://', '').split('/')
            if len(url_parts) >= 3:
                container_name = url_parts[1]
                blob_name = '/'.join(url_parts[2:])
            else:
                return web.json_response({'error': 'Invalid blob URL format'}, status=400)
        
        if not blob_name or not container_name:
            return web.json_response({'error': 'blob_name and container_name are required'}, status=400)
        
        # Validate file type
        file_extension = blob_name.lower().split('.')[-1] if '.' in blob_name else ''
        supported_types = ALL_SUPPORTED_EXTENSIONS
        
        if file_extension not in supported_types:
            logger.info(f"Skipping unsupported file type: {blob_name} (type: {file_extension})")
            return web.json_response({'status': 'skipped', 'reason': f'Unsupported file type: {file_extension}'})
        
        # Process the file
        await processor.process_file(blob_name, container_name)
        
        return web.json_response({'status': 'success', 'message': f'Processed {blob_name} from {container_name}'})
        
    except Exception as e:
        logger.error(f"Error processing event: {e}")
        return web.json_response({'status': 'error', 'error': str(e)}, status=500)


async def health_check(request):
    """Health check endpoint"""
    return web.json_response({
        'status': 'healthy', 
        'timestamp': datetime.utcnow().isoformat(),
        'configuration': {
            'chunk_max_tokens': CHUNK_MAX_TOKENS,
            'embedding_max_tokens': EMBEDDING_MAX_TOKENS,
            'encoding_model': ENCODING_MODEL,
            'max_file_size_mb': MAX_FILE_SIZE_MB,
            'concurrent_message_processing': CONCURRENT_MESSAGE_PROCESSING,
            'concurrent_file_processing': CONCURRENT_FILE_PROCESSING,
            'max_retries': MAX_RETRIES,
            'retry_delay_seconds': RETRY_DELAY_SECONDS,
            'rate_limit_base_wait': RATE_LIMIT_BASE_WAIT,
            'rate_limit_max_wait': RATE_LIMIT_MAX_WAIT
        }
    })


async def readiness_check(request):
    """Readiness check endpoint"""
    try:
        # Check if clients are initialized
        required_clients = [processor.blob_client, processor.search_client, processor.openai_client]
        
        # Service Bus is optional (might use webhooks instead)
        if SERVICEBUS_NAMESPACE:
            required_clients.append(processor.servicebus_client)
        
        if any(client is None for client in required_clients):
            return web.json_response({
                'status': 'not ready', 
                'message': 'Clients not initialized',
                'clients': {
                    'blob_client': processor.blob_client is not None,
                    'search_client': processor.search_client is not None,
                    'openai_client': processor.openai_client is not None,
                    'servicebus_client': processor.servicebus_client is not None if SERVICEBUS_NAMESPACE else 'not configured'
                }
            }, status=503)
        
        return web.json_response({
            'status': 'ready', 
            'timestamp': datetime.utcnow().isoformat(),
            'clients_initialized': True,
            'processing_mode': 'servicebus' if SERVICEBUS_NAMESPACE else 'webhook'
        })
    except Exception as e:
        return web.json_response({'status': 'not ready', 'error': str(e)}, status=503)


async def manual_process(request):
    """Manual processing endpoint for testing"""
    try:
        # This endpoint can be used for manual testing
        # Expected JSON: {"blob_name": "test.pdf", "container_name": "documents"}
        request_data = await request.json()
        blob_name = request_data.get('blob_name')
        container_name = request_data.get('container_name')
        
        if not blob_name or not container_name:
            return web.json_response({'error': 'blob_name and container_name are required'}, status=400)
        
        await processor.process_file(blob_name, container_name)
        
        return web.json_response({
            'status': 'success',
            'message': f'Processed {blob_name} from {container_name}',
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Manual processing failed: {e}")
        return web.json_response({'status': 'error', 'error': str(e)}, status=500)


def create_app():
    """Create the aiohttp application"""
    app = web.Application()
    
    # Add routes
    app.router.add_get('/health', health_check)
    app.router.add_get('/ready', readiness_check)
    app.router.add_post('/process', manual_process)
    app.router.add_post('/webhook', process_blob_event)  # Event Grid webhook
    
    return app

async def main():
    """Main application entry point"""
    logger.info("Starting Azure File Processing Microservice with concurrent processing and intelligent chunking...")
    logger.info(f"Configuration: "
               f"CHUNK_MAX_TOKENS={CHUNK_MAX_TOKENS}, "
               f"EMBEDDING_MAX_TOKENS={EMBEDDING_MAX_TOKENS}, "
               f"MAX_FILE_SIZE_MB={MAX_FILE_SIZE_MB}, "
               f"CONCURRENT_MESSAGE_PROCESSING={CONCURRENT_MESSAGE_PROCESSING}, "
               f"CONCURRENT_FILE_PROCESSING={CONCURRENT_FILE_PROCESSING}, "
               f"MAX_RETRIES={MAX_RETRIES}")
    
    # Initialize the processor
    await processor.initialize()
    
    # Create the web application
    app = create_app()
    
    # Start the web server
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
    await site.start()
    
    logger.info(f"Server started on port {HTTP_PORT}")
    logger.info(f"Health check: http://{HTTP_LOCALHOST}:{HTTP_PORT}/health")
    logger.info(f"Ready check: http://{HTTP_LOCALHOST}:{HTTP_PORT}/ready")
    logger.info(f"Process endpoint: http://{HTTP_LOCALHOST}:{HTTP_PORT}/process")
    logger.info(f"Webhook endpoint: http://{HTTP_LOCALHOST}:{HTTP_PORT}/webhook")
    
    # Start Service Bus processing if configured
    servicebus_task = None
    if SERVICEBUS_NAMESPACE:
        logger.info(f"Starting Service Bus processing for namespace: {SERVICEBUS_NAMESPACE}")
        servicebus_task = asyncio.create_task(processor.start_service_bus_processing())
    else:
        logger.info("Service Bus not configured - using webhook mode only")
    
    logger.info("File Processor microservice started successfully")
    
    # Keep the server running
    try:
        while True:
            await asyncio.sleep(MAIN_LOOP_SLEEP_SECONDS)  # Sleep for 1 hour
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        # Clean shutdown
        if servicebus_task:
            await processor.stop_service_bus_processing()
            servicebus_task.cancel()
            try:
                await servicebus_task
            except asyncio.CancelledError:
                pass
        
        await runner.cleanup()

if __name__ == '__main__':
    # Start the aiohttp application
    logger.info(f"Starting File Processor microservice on port {HTTP_PORT}")
    asyncio.run(main())
