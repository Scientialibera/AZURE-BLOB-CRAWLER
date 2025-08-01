"""
Service Bus message processing service

This module handles Azure Service Bus message processing with concurrent workers
and automatic message handling for blob creation events.
"""

import json
import asyncio
import logging
from typing import Optional

from azure_clients import create_credential, DirectServiceBusClient
from processing import DocumentProcessor
from utils.exceptions import BlobNotFoundError, ProcessingSkippedError, TokenAcquisitionError
from config.settings import (
    SERVICEBUS_NAMESPACE, SERVICEBUS_QUEUE_NAME, SERVICEBUS_ENDPOINT_SUFFIX,
    SERVICEBUS_MAX_MESSAGES, SERVICEBUS_WAIT_TIME, CONCURRENT_MESSAGE_PROCESSING,
    ERROR_RETRY_SLEEP_SECONDS, TOKEN_PRE_WARMING_ENABLED, VERBOSE_BATCH_LOGGING
)

logger = logging.getLogger(__name__)


class ServiceBusProcessor:
    """
    Handles Azure Service Bus message processing
    
    This class manages Service Bus message reception and processing with
    concurrent workers and automatic error handling.
    """
    
    def __init__(self, document_processor: DocumentProcessor):
        """
        Initialize the Service Bus processor
        
        Args:
            document_processor: Document processor instance
        """
        self.document_processor = document_processor
        self.credential = create_credential()
        self.servicebus_client: Optional[DirectServiceBusClient] = None
        self.servicebus_receiver = None
        self._processing = False
        
    async def initialize(self):
        """
        Initialize Service Bus client and receiver
        
        Raises:
            Exception: If Service Bus initialization fails
        """
        try:
            if SERVICEBUS_NAMESPACE:
                self.servicebus_client = DirectServiceBusClient(
                    namespace_url=f"https://{SERVICEBUS_NAMESPACE}{SERVICEBUS_ENDPOINT_SUFFIX}",
                    credential=self.credential
                )
                
                # Create receiver for the queue
                self.servicebus_receiver = self.servicebus_client.get_queue_receiver(
                    queue_name=SERVICEBUS_QUEUE_NAME,
                    max_wait_time=SERVICEBUS_WAIT_TIME
                )
                logger.info(f"   INITIALIZED Service Bus client for {SERVICEBUS_NAMESPACE}")
                
                # Pre-warm Service Bus token (if enabled)
                if TOKEN_PRE_WARMING_ENABLED and self.servicebus_client:
                    logger.info("   Pre-warming Service Bus token...")
                    try:
                        await self.servicebus_client.pre_warm_token()
                        logger.info("   Service Bus token pre-warming successful")
                    except Exception as e:
                        logger.warning(f"   Service Bus token pre-warming failed: {e}")
            else:
                logger.info("   Service Bus not configured - using webhook mode only")
                
        except Exception as e:
            logger.error(f"   Failed to initialize Service Bus: {e}")
            raise

    async def start_processing(self):
        """
        Start processing Service Bus messages with concurrent processing
        
        This method runs continuously, receiving and processing messages
        from the Service Bus queue using multiple concurrent workers.
        """
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
                    
                    if VERBOSE_BATCH_LOGGING:
                        logger.info(f"Received {len(received_msgs)} messages for concurrent processing")
                    
                    # Process messages concurrently using asyncio.gather with semaphore for rate limiting
                    semaphore = asyncio.Semaphore(CONCURRENT_MESSAGE_PROCESSING)
                    
                    async def process_single_message_with_semaphore(msg):
                        async with semaphore:
                            return await self._process_single_message(msg)
                    
                    # Process all messages concurrently
                    tasks = [process_single_message_with_semaphore(msg) for msg in received_msgs]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log results with more detail only if verbose logging is enabled
                    if VERBOSE_BATCH_LOGGING:
                        successful = sum(1 for result in results if result is True)
                        failed = len(results) - successful
                        logger.info(f"Batch processing complete - Success: {successful}, Failed: {failed}")
                        
                        # Log any specific exceptions for debugging
                        for i, result in enumerate(results):
                            if isinstance(result, Exception):
                                logger.debug(f"Message {i} failed with exception: {result}")
                    else:
                        # Only log if there are failures when not in verbose mode
                        failed_count = sum(1 for result in results if isinstance(result, Exception))
                        if failed_count > 0:
                            logger.warning(f"Processed {len(results)} messages - {failed_count} failed")
                    
                except Exception as e:
                    logger.error(f"Error receiving messages: {e}")
                    await asyncio.sleep(ERROR_RETRY_SLEEP_SECONDS)  # Wait before retry
                    
        except Exception as e:
            logger.error(f"Service Bus processing error: {e}")
        finally:
            logger.info("Service Bus message processing stopped")

    async def _process_single_message(self, msg) -> bool:
        """
        Process a single Service Bus message
        
        Args:
            msg: Service Bus message to process
            
        Returns:
            bool: True if processing successful, False otherwise
        """
        blob_name = "unknown"  # Initialize with default value for logging
        container_name = "unknown"
        
        try:
            # Parse message body
            message_body = str(msg)
            logger.info(f"Processing message: {message_body}")
            
            # Try to parse as JSON
            try:
                message_data = json.loads(message_body)
            except json.JSONDecodeError:
                logger.warning(f"Message not in JSON format, completing message: {message_body}")
                await self.servicebus_receiver.complete_message(msg)
                if VERBOSE_BATCH_LOGGING:
                    logger.info("Message completed due to invalid JSON format")
                return True
            
            # Extract blob information
            # blob_name = None  # Remove this line since we initialized above
            # container_name = None  # Remove this line since we initialized above
            
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
                if VERBOSE_BATCH_LOGGING:
                    logger.info("Message completed due to invalid blob information")
                return True
            
            # Process the file
            await self.document_processor.process_file(blob_name, container_name)
            
            # Complete the message
            await self.servicebus_receiver.complete_message(msg)
            if VERBOSE_BATCH_LOGGING:
                logger.info(f"Successfully processed and completed message for {blob_name}")
            return True
            
        except (BlobNotFoundError, ProcessingSkippedError) as e:
            # These are expected conditions that don't require retry
            logger.warning(f"Processing completed with expected condition for {blob_name}: {e}")
            # Complete the message - don't retry for these conditions
            try:
                await self.servicebus_receiver.complete_message(msg)
                if VERBOSE_BATCH_LOGGING:
                    logger.info(f"Message marked as completed (skipped) for {blob_name}")
            except Exception as complete_error:
                logger.error(f"Failed to complete message after skipping: {complete_error}")
            return True
            
        except TokenAcquisitionError as e:
            # Token acquisition failures - might be temporary, so abandon for retry
            logger.error(f"Token acquisition failed for {blob_name}: {e}")
            try:
                await self.servicebus_receiver.abandon_message(msg)
                logger.info(f"Message abandoned for retry due to token acquisition failure: {blob_name}")
            except Exception as abandon_error:
                logger.error(f"Failed to abandon message after token error: {abandon_error}")
            return False
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Abandon message to allow retry for unexpected errors
            try:
                await self.servicebus_receiver.abandon_message(msg)
            except Exception as abandon_error:
                logger.error(f"Failed to abandon message: {abandon_error}")
            return False

    async def stop_processing(self):
        """Stop Service Bus message processing"""
        self._processing = False
        if self.servicebus_receiver:
            await self.servicebus_receiver.close()
        if self.servicebus_client:
            await self.servicebus_client.close()
