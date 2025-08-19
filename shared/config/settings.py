"""
Configuration settings for Azure File Processing Microservice

All environment variables and constants are centralized here for easy management.
"""

import os

# ====== AZURE SERVICE CONFIGURATION ======
STORAGE_ACCOUNT_NAME = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
SEARCH_SERVICE_NAME = os.getenv('AZURE_SEARCH_SERVICE_NAME')
OPENAI_SERVICE_NAME = os.getenv('AZURE_OPENAI_SERVICE_NAME')
SEARCH_INDEX_NAME = os.getenv('AZURE_SEARCH_INDEX_NAME', 'documents')
SERVICEBUS_NAMESPACE = os.getenv('SERVICEBUS_NAMESPACE')
SERVICEBUS_QUEUE_NAME = os.getenv('SERVICEBUS_QUEUE_NAME', 'indexqueue')

# ====== AUTHENTICATION CONFIGURATION ======
TOKEN_LF = int(os.getenv('TOKEN_LIFETIME_MINUTES', '45'))  # Token lifetime in minutes
TOKEN_ACQUISITION_TIMEOUT_SECONDS = int(os.getenv('TOKEN_ACQUISITION_TIMEOUT_SECONDS', '30'))  # Timeout for token acquisition
TOKEN_PRE_WARMING_ENABLED = os.getenv('TOKEN_PRE_WARMING_ENABLED', 'true').lower() == 'true'  # Enable token pre-warming at startup
DELETE_BLOB_AFTER_PROCESSING = os.getenv('DELETE_BLOB_AFTER_PROCESSING', 'true').lower() == 'true'  # Delete blob after successful processing
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")  # User-assigned managed identity client ID
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")  # Azure tenant ID for token validation

# ====== API VERSIONS ======
OPENAI_API_VERSION = os.getenv('OPENAI_API_VERSION', '2023-05-15')  # Match AI Foundry version
SEARCH_API_VERSION = os.getenv('SEARCH_API_VERSION', '2024-07-01')
STORAGE_API_VERSION = os.getenv('STORAGE_API_VERSION', '2023-11-03')  # Azure Storage REST API version
OPENAI_EMBEDDING_MODEL = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-ada-002')

# ====== TOKEN LIMITS AND CHUNKING ======
CHUNK_MAX_TOKENS = int(os.getenv('CHUNK_MAX_TOKENS', '4000'))  # Max tokens per chunk for processing
EMBEDDING_MAX_TOKENS = int(os.getenv('EMBEDDING_MAX_TOKENS', '8000'))  # Max tokens for embedding (OpenAI limit)
OVERLAP_TOKENS = int(os.getenv('OVERLAP_TOKENS', '200'))  # Token overlap between chunks
ENCODING_MODEL = os.getenv('ENCODING_MODEL', 'cl100k_base')  # Tiktoken encoding model

# ====== FILE PROCESSING LIMITS ======
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '100'))  # Maximum file size in MB
MAX_PAGES_PER_CHUNK = int(os.getenv('MAX_PAGES_PER_CHUNK', '10'))  # For PDF/DOCX chunking

# ====== RETRY AND TIMEOUT CONFIGURATION ======
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
RETRY_DELAY_SECONDS = int(os.getenv('RETRY_DELAY_SECONDS', '2'))
REQUEST_TIMEOUT_SECONDS = int(os.getenv('REQUEST_TIMEOUT_SECONDS', '60'))
# HTTP status codes that indicate permanent failures and should not be retried
# Default: 400 (Bad Request), 401 (Unauthorized), 403 (Forbidden), 404 (Not Found), 
#          405 (Method Not Allowed), 409 (Conflict), 422 (Unprocessable Entity)
SKIP_RETRY_CODES = [int(code.strip()) for code in os.getenv('SKIP_RETRY_CODES', '400,401,403,404,405,409,422').split(',') if code.strip()]

# ====== RATE LIMIT HANDLING ======
RATE_LIMIT_BASE_WAIT = int(os.getenv('RATE_LIMIT_BASE_WAIT', '60'))  # Base wait time for rate limits
RATE_LIMIT_MAX_WAIT = int(os.getenv('RATE_LIMIT_MAX_WAIT', '300'))  # Maximum wait time for rate limits

# ====== HTTP SERVER CONFIGURATION ======
HTTP_PORT = int(os.getenv('HTTP_PORT', '50051'))  # Server port
HTTP_HOST = os.getenv('HTTP_HOST', '0.0.0.0')  # Server host
HTTP_LOCALHOST = os.getenv('HTTP_LOCALHOST', 'localhost')  # Localhost for logging

# ====== AZURE SERVICE ENDPOINTS AND SCOPES ======
AZURE_MANAGEMENT_SCOPE = "https://management.azure.com/.default"
AZURE_SEARCH_SCOPE = "https://search.azure.com/.default"
AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
AZURE_STORAGE_SCOPE = "https://storage.azure.com/.default"
AZURE_SERVICEBUS_SCOPE = "https://servicebus.azure.net/.default"
BLOB_ENDPOINT_SUFFIX = ".blob.core.windows.net"
SEARCH_ENDPOINT_SUFFIX = ".search.windows.net"
SERVICEBUS_ENDPOINT_SUFFIX = ".servicebus.windows.net"

# ====== OPENAI ENDPOINT CONFIGURATION ======
OPENAI_ENDPOINT_BASE = os.getenv('OPENAI_ENDPOINT_BASE', 
    f'https://{OPENAI_SERVICE_NAME}.openai.azure.com' if OPENAI_SERVICE_NAME 
    else 'https://eastus2.api.cognitive.microsoft.com'
)

# ====== EMBEDDING MODEL CONFIGURATION ======
EMBEDDING_VECTOR_DIMENSION = int(os.getenv('EMBEDDING_VECTOR_DIMENSION', '1536'))  # text-embedding-ada-002 dimensions
EMBEDDING_FALLBACK_TOKEN_RATIO = int(os.getenv('EMBEDDING_FALLBACK_TOKEN_RATIO', '4'))  # 1 token ≈ 4 characters

# ====== SERVICE BUS CONFIGURATION ======
SERVICEBUS_MAX_MESSAGES = int(os.getenv('SERVICEBUS_MAX_MESSAGES', '10'))  # Max messages per batch
SERVICEBUS_WAIT_TIME = int(os.getenv('SERVICEBUS_WAIT_TIME', '5'))  # Wait time in seconds
SERVICEBUS_LOCK_RENEWAL_ENABLED = os.getenv('SERVICEBUS_LOCK_RENEWAL_ENABLED', 'true').lower() == 'true'  # Enable automatic lock renewal
SERVICEBUS_LOCK_RENEWAL_INTERVAL = int(os.getenv('SERVICEBUS_LOCK_RENEWAL_INTERVAL', '20'))  # Lock renewal interval in seconds
SERVICEBUS_LOCK_DURATION = int(os.getenv('SERVICEBUS_LOCK_DURATION', '30'))  # Default lock duration in seconds
SERVICEBUS_MAX_DELIVERY_COUNT = int(os.getenv('SERVICEBUS_MAX_DELIVERY_COUNT', '10'))  # Max delivery attempts before dead letter

# ====== CONCURRENT PROCESSING ======
CONCURRENT_MESSAGE_PROCESSING = int(os.getenv('CONCURRENT_MESSAGE_PROCESSING', '5'))  # Number of concurrent message processing tasks
CONCURRENT_FILE_PROCESSING = int(os.getenv('CONCURRENT_FILE_PROCESSING', '3'))  # Number of concurrent file processing operations

# ====== FILE TYPE SUPPORT ======
SUPPORTED_TEXT_EXTENSIONS = ['txt', 'md', 'csv']
SUPPORTED_STRUCTURED_EXTENSIONS = ['json']
SUPPORTED_DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'doc']
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_TEXT_EXTENSIONS + SUPPORTED_STRUCTURED_EXTENSIONS + SUPPORTED_DOCUMENT_EXTENSIONS

# ====== DOCUMENT PROCESSING CONSTANTS ======
PARAGRAPHS_PER_PAGE = int(os.getenv('PARAGRAPHS_PER_PAGE', '20'))  # Artificial page breaks for DOCX
PAGE_PREFIX = "--- Page "
SECTION_PREFIX = "--- Section "
PAGE_SUFFIX = " ---"

# ====== TEXT ENCODING ======
TEXT_ENCODING = 'utf-8'
TEXT_ENCODING_ERRORS = 'ignore'
TIKTOKEN_FALLBACK_MODEL = 'cl100k_base'

# ====== HTTP CONSTANTS ======
HTTP_CONTENT_TYPE_JSON = 'application/json'
HTTP_AUTH_BEARER_PREFIX = 'Bearer'
HTTP_SUCCESS_CODES = [200, 201]

# ====== SEARCH API CONSTANTS ======
SEARCH_ACTION_UPLOAD = 'upload'
SEARCH_ACTION_DELETE = 'delete'
SEARCH_DOCS_INDEX_PATH = '/indexes/{}/docs/index'
SEARCH_DOCS_SEARCH_PATH = '/indexes/{}/docs/search'
OPENAI_EMBEDDINGS_PATH = '/openai/deployments/{}/embeddings'

# ====== DOCUMENT FIELD NAMES ======
DOCUMENT_ID_FIELD = 'id'
DOCUMENT_CONTENT_FIELD = 'content'
DOCUMENT_VECTOR_FIELD = 'vector'
SEARCH_ACTION_FIELD = '@search.action'

# ====== LOGGING CONFIGURATION ======
TOKEN_PREVIEW_LENGTH = int(os.getenv('TOKEN_PREVIEW_LENGTH', '20'))  # Length of token preview in logs
VECTOR_DISPLAY_TEXT = "[Vector with {} dimensions]"
DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'US/Eastern')  # For logging timestamps

# Logging verbosity controls
VERBOSE_RETRY_LOGGING = os.getenv('VERBOSE_RETRY_LOGGING', 'false').lower() == 'true'  # Log all retry attempts
VERBOSE_AUTH_LOGGING = os.getenv('VERBOSE_AUTH_LOGGING', 'false').lower() == 'true'  # Log token checking details
VERBOSE_BATCH_LOGGING = os.getenv('VERBOSE_BATCH_LOGGING', 'True').lower() == 'true'  # Log detailed batch results

# ====== PROCESSING INTERVALS ======
MAIN_LOOP_SLEEP_SECONDS = int(os.getenv('MAIN_LOOP_SLEEP_SECONDS', '3600'))  # 1 hour
ERROR_RETRY_SLEEP_SECONDS = int(os.getenv('ERROR_RETRY_SLEEP_SECONDS', '5'))  # Error retry delay

# ====== MCP SERVER CONFIGURATION ======
MCP_SERVER_NAME = os.getenv('MCP_SERVER_NAME', 'azure-search-mcp')
MCP_SERVER_VERSION = os.getenv('MCP_SERVER_VERSION', '1.0.0')
MCP_PORT = int(os.getenv('MCP_PORT', '8080'))  # MCP server port
SEARCH_DEFAULT_TOP = int(os.getenv('SEARCH_DEFAULT_TOP', '10'))  # Default number of search results
SEARCH_MAX_TOP = int(os.getenv('SEARCH_MAX_TOP', '100'))  # Maximum number of search results
SEARCH_ALL_DOCS_MAX = int(os.getenv('SEARCH_ALL_DOCS_MAX', '100000'))  # Maximum number of documents for get-all-docs
EXCLUDED_FIELDS = os.getenv('EXCLUDED_FIELDS', 'vector').split(',')  # Fields to exclude from search results
