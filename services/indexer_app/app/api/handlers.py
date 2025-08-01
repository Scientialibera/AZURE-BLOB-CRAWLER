"""
HTTP API handlers for the file processing microservice

This module provides HTTP endpoints for health checks, readiness checks,
manual processing, and webhook handling.
"""

import json
import logging
import sys
import os
from datetime import datetime
from aiohttp import web

# Add shared directory to Python path
# Handle both Docker environment (/app/shared) and development environment
shared_path = '/app/shared' if os.path.exists('/app/shared') else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), 'shared')
sys.path.insert(0, shared_path)

from shared.processing import DocumentProcessor
from shared.config.settings import (
    ALL_SUPPORTED_EXTENSIONS, CHUNK_MAX_TOKENS, EMBEDDING_MAX_TOKENS,
    ENCODING_MODEL, MAX_FILE_SIZE_MB, CONCURRENT_MESSAGE_PROCESSING,
    CONCURRENT_FILE_PROCESSING, MAX_RETRIES, RETRY_DELAY_SECONDS,
    RATE_LIMIT_BASE_WAIT, RATE_LIMIT_MAX_WAIT, SERVICEBUS_NAMESPACE
)

logger = logging.getLogger(__name__)


class APIHandlers:
    """
    HTTP API handlers for the microservice
    
    This class provides all the HTTP endpoint handlers for health checks,
    processing requests, and webhook handling.
    """
    
    def __init__(self, document_processor: DocumentProcessor):
        """
        Initialize API handlers
        
        Args:
            document_processor: Document processor instance
        """
        self.document_processor = document_processor
    
    async def health_check(self, request):
        """
        Health check endpoint
        
        Returns:
            JSON response with service health status and configuration
        """
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

    async def readiness_check(self, request):
        """
        Readiness check endpoint
        
        Returns:
            JSON response with service readiness status
        """
        try:
            # Check if clients are initialized
            required_clients = [
                self.document_processor.blob_client, 
                self.document_processor.search_client, 
                self.document_processor.openai_client
            ]
            
            # Service Bus is optional (might use webhooks instead)
            servicebus_status = 'not configured'
            if SERVICEBUS_NAMESPACE:
                servicebus_status = hasattr(self.document_processor, 'servicebus_client')
            
            if any(client is None for client in required_clients):
                return web.json_response({
                    'status': 'not ready', 
                    'message': 'Clients not initialized',
                    'clients': {
                        'blob_client': self.document_processor.blob_client is not None,
                        'search_client': self.document_processor.search_client is not None,
                        'openai_client': self.document_processor.openai_client is not None,
                        'servicebus_client': servicebus_status
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

    async def manual_process(self, request):
        """
        Manual processing endpoint for testing
        
        Expected JSON: {"blob_name": "test.pdf", "container_name": "documents"}
        
        Returns:
            JSON response with processing result
        """
        try:
            request_data = await request.json()
            blob_name = request_data.get('blob_name')
            container_name = request_data.get('container_name')
            
            if not blob_name or not container_name:
                return web.json_response({'error': 'blob_name and container_name are required'}, status=400)
            
            await self.document_processor.process_file(blob_name, container_name)
            
            return web.json_response({
                'status': 'success',
                'message': f'Processed {blob_name} from {container_name}',
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Manual processing failed: {e}")
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)

    async def process_blob_event(self, request):
        """
        Handle blob creation events from HTTP webhook
        
        Returns:
            JSON response with processing result
        """
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
            blob_name = None
            container_name = None
            
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
            
            if file_extension not in ALL_SUPPORTED_EXTENSIONS:
                logger.info(f"Skipping unsupported file type: {blob_name} (type: {file_extension})")
                return web.json_response({'status': 'skipped', 'reason': f'Unsupported file type: {file_extension}'})
            
            # Process the file
            await self.document_processor.process_file(blob_name, container_name)
            
            return web.json_response({'status': 'success', 'message': f'Processed {blob_name} from {container_name}'})
            
        except Exception as e:
            logger.error(f"Error processing event: {e}")
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)
