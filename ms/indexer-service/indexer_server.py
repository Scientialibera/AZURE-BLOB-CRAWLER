"""
Azure File Processing Microservice - Indexer Server

This is the main entry point for the Azure File Processing Indexer Service.
It orchestrates the initialization of all components and starts the HTTP server
and Service Bus processing.

Features:
- Event-driven processing via Azure Service Bus SDK
- Direct HTTP calls to Azure OpenAI and Azure AI Search with token authentication
- Content extraction from various file types (TXT, PDF, DOCX, JSON)
- Intelligent chunking with token-based limits
- Modular architecture with proper separation of concerns
"""

import asyncio
import logging
import sys
import os
from aiohttp import web

# Add shared modules to path
shared_path = os.path.join(os.path.dirname(__file__), 'shared')
if os.path.exists(shared_path):
    sys.path.append(shared_path)
else:
    # Fallback for development environment
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from config.settings import (
    HTTP_HOST, HTTP_PORT, HTTP_LOCALHOST, SERVICEBUS_NAMESPACE,
    MAIN_LOOP_SLEEP_SECONDS, CHUNK_MAX_TOKENS, EMBEDDING_MAX_TOKENS,
    MAX_FILE_SIZE_MB, CONCURRENT_MESSAGE_PROCESSING, CONCURRENT_FILE_PROCESSING,
    MAX_RETRIES
)
from processing import DocumentProcessor
from services import ServiceBusProcessor
from api import APIHandlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(api_handlers: APIHandlers) -> web.Application:
    """
    Create the aiohttp application with all routes
    
    Args:
        api_handlers: API handlers instance
        
    Returns:
        web.Application: Configured aiohttp application
    """
    app = web.Application()
    
    # Add routes
    app.router.add_get('/health', api_handlers.health_check)
    app.router.add_get('/ready', api_handlers.readiness_check)
    app.router.add_post('/process', api_handlers.manual_process)
    app.router.add_post('/webhook', api_handlers.process_blob_event)  # Event Grid webhook
    
    return app


async def main():
    """
    Main application entry point
    
    This function initializes all components, starts the HTTP server,
    and optionally starts Service Bus processing.
    """
    logger.info("Starting Azure File Processing Microservice with modular architecture...")
    logger.info(f"Configuration: "
               f"CHUNK_MAX_TOKENS={CHUNK_MAX_TOKENS}, "
               f"EMBEDDING_MAX_TOKENS={EMBEDDING_MAX_TOKENS}, "
               f"MAX_FILE_SIZE_MB={MAX_FILE_SIZE_MB}, "
               f"CONCURRENT_MESSAGE_PROCESSING={CONCURRENT_MESSAGE_PROCESSING}, "
               f"CONCURRENT_FILE_PROCESSING={CONCURRENT_FILE_PROCESSING}, "
               f"MAX_RETRIES={MAX_RETRIES}")
    
    # Initialize the document processor
    document_processor = DocumentProcessor()
    await document_processor.initialize()
    
    # Initialize API handlers
    api_handlers = APIHandlers(document_processor)
    
    # Create the web application
    app = create_app(api_handlers)
    
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
    
    # Initialize and start Service Bus processing if configured
    servicebus_task = None
    servicebus_processor = None
    
    if SERVICEBUS_NAMESPACE:
        logger.info(f"Starting Service Bus processing for namespace: {SERVICEBUS_NAMESPACE}")
        servicebus_processor = ServiceBusProcessor(document_processor)
        await servicebus_processor.initialize()
        servicebus_task = asyncio.create_task(servicebus_processor.start_processing())
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
        if servicebus_processor and servicebus_task:
            await servicebus_processor.stop_processing()
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
