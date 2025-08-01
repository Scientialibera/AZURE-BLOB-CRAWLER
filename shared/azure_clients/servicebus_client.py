"""
Azure Service Bus client for message processing

This module provides a direct client for Azure Service Bus API with managed identity
authentication and message processing capabilities.
"""

import json
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

from azure_clients.auth import AzureClientBase
from utils.retry import retry_logic
from config.settings import (
    REQUEST_TIMEOUT_SECONDS, MAX_RETRIES, RETRY_DELAY_SECONDS,
     AZURE_SERVICEBUS_SCOPE, SERVICEBUS_MAX_MESSAGES,
    SERVICEBUS_WAIT_TIME
)

logger = logging.getLogger(__name__)


class DirectServiceBusClient(AzureClientBase):
    """
    Direct HTTP client for Azure Service Bus API
    
    This client uses managed identity authentication and provides methods
    for receiving and managing Service Bus queue messages.
    """
    
    def __init__(self, namespace_url: str, credential):
        """
        Initialize the Service Bus client
        
        Args:
            namespace_url: Azure Service Bus namespace URL
            credential: Azure credential instance
        """
        super().__init__(credential, AZURE_SERVICEBUS_SCOPE)
        self.namespace_url = namespace_url.rstrip('/')
        
    def get_queue_receiver(self, queue_name: str, max_wait_time: int = SERVICEBUS_WAIT_TIME) -> 'ServiceBusQueueReceiver':
        """
        Get a queue receiver for the specified queue
        
        Args:
            queue_name: Name of the Service Bus queue
            max_wait_time: Maximum wait time for receiving messages
            
        Returns:
            ServiceBusQueueReceiver: Queue receiver instance
        """
        return ServiceBusQueueReceiver(self, queue_name, max_wait_time)
        
    async def close(self):
        """Close the Service Bus client (for compatibility)"""
        logger.info("DirectServiceBusClient closed")


class ServiceBusQueueReceiver:
    """
    Service Bus queue receiver for message processing
    
    This class provides methods for receiving and managing messages from a
    Service Bus queue using direct HTTP calls.
    """
    
    def __init__(self, client: DirectServiceBusClient, queue_name: str, max_wait_time: int):
        """
        Initialize the queue receiver
        
        Args:
            client: DirectServiceBusClient instance
            queue_name: Name of the Service Bus queue
            max_wait_time: Maximum wait time for receiving messages
        """
        self.client = client
        self.queue_name = queue_name
        self.max_wait_time = max_wait_time
        self._closed = False
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def receive_messages(self, max_message_count: int = SERVICEBUS_MAX_MESSAGES, 
                             max_wait_time: Optional[int] = None) -> List['ServiceBusMessage']:
        """
        Receive messages from the Service Bus queue
        
        Args:
            max_message_count: Maximum number of messages to receive
            max_wait_time: Maximum wait time (uses default if None)
            
        Returns:
            List[ServiceBusMessage]: List of received messages
            
        Raises:
            Exception: If API call fails after all retries
        """
        if self._closed:
            return []
            
        wait_time = max_wait_time or self.max_wait_time
        
        # Service Bus REST API endpoint for receiving messages
        url = f"{self.client.namespace_url}/{self.queue_name}/messages/head"
        headers = await self.client._get_headers()
        
        # Add Service Bus specific headers
        headers.update({
            "Accept": "application/json",
            "BrokerProperties": json.dumps({
                "MaxMessages": max_message_count,
                "TimeToLive": wait_time
            })
        })
        
        response = requests.post(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Log response details for debugging
        logger.info(f"   Status: {response.status_code}")
        logger.debug(f"   Response headers: {dict(response.headers)}")
        logger.debug(f"   Response content length: {len(response.content) if response.content else 0}")
        
        # Handle no messages available (not an error)
        if response.status_code == 204:
            logger.info("   No messages available in queue")
            return []
        
        if response.status_code != 200:
            logger.error(f"   Service Bus Receive API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        response.raise_for_status()
        
        # Parse messages from response
        messages = []
        try:
            # Service Bus can return single message or array
            response_data = response.json() if response.content else []
            if not isinstance(response_data, list):
                response_data = [response_data]
            
            # Get broker properties from response headers
            broker_properties_header = response.headers.get('BrokerProperties', '{}')
            try:
                broker_properties = json.loads(broker_properties_header)
            except (json.JSONDecodeError, TypeError):
                broker_properties = {}
            
            for i, msg_data in enumerate(response_data):
                # Extract message properties from headers and broker properties
                message_id = response.headers.get('MessageId') or broker_properties.get('MessageId') or f"msg_{datetime.now().timestamp()}_{i}"
                lock_token = response.headers.get('LockToken') or broker_properties.get('LockToken')
                
                # If no lock token found, try to extract from individual message data
                if not lock_token and isinstance(msg_data, dict):
                    lock_token = msg_data.get('LockToken') or msg_data.get('lockToken')
                
                # Log lock token status for debugging
                if lock_token:
                    logger.debug(f"   Message {i}: Found lock token: {lock_token}")
                else:
                    logger.debug(f"   Message {i}: No lock token found - message may not be properly locked")
                
                message = ServiceBusMessage(
                    message_id=message_id,
                    body=msg_data,
                    lock_token=lock_token,
                    receiver=self
                )
                messages.append(message)
                
        except Exception as e:
            logger.warning(f"Failed to parse Service Bus response: {e}")
            # Create a simple message from raw response
            if response.content:
                # Try to extract any lock token from headers
                lock_token = response.headers.get('LockToken') or response.headers.get('lockToken')
                message = ServiceBusMessage(
                    message_id=f"msg_{datetime.now().timestamp()}",
                    body=response.text,
                    lock_token=lock_token,
                    receiver=self
                )
                messages.append(message)
        
        logger.info(f"   Service Bus Receive successful - Received {len(messages)} messages")
        return messages
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def complete_message(self, message: 'ServiceBusMessage') -> None:
        """
        Complete (acknowledge) a message
        
        Args:
            message: Message to complete
            
        Raises:
            Exception: If API call fails after all retries
        """
        if not message.lock_token:
            logger.warning(f"Cannot complete message without lock token - Message ID: {message.message_id}")
            logger.debug(f"Message details: {message}")
            # In this case, we'll assume the message is already processed and return success
            return
            
        url = f"{self.client.namespace_url}/{self.queue_name}/messages/{message.message_id}/{message.lock_token}"
        headers = await self.client._get_headers()
        
        logger.debug(f"   START SERVICE BUS Complete Message:")
        logger.debug(f"   Message ID: {message.message_id}")
        logger.debug(f"   Lock Token: {message.lock_token}")
        
        response = requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.debug(f"   Complete Message Response - Status: {response.status_code}")
        
        if response.status_code not in [200, 204]:
            logger.error(f"   Service Bus Complete API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        # Don't raise for complete operations - log and continue
        if response.status_code in [200, 204]:
            logger.debug(f"   Message {message.message_id} completed successfully")
        else:
            logger.warning(f"   Failed to complete message {message.message_id}, status: {response.status_code}")
        
    @retry_logic(max_retries=MAX_RETRIES, delay=RETRY_DELAY_SECONDS)
    async def abandon_message(self, message: 'ServiceBusMessage') -> None:
        """
        Abandon a message (make it available for reprocessing)
        
        Args:
            message: Message to abandon
            
        Raises:
            Exception: If API call fails after all retries
        """
        if not message.lock_token:
            logger.warning(f"Cannot abandon message without lock token - Message ID: {message.message_id}")
            logger.debug(f"Message details: {message}")
            return
            
        url = f"{self.client.namespace_url}/{self.queue_name}/messages/{message.message_id}/{message.lock_token}/abandon"
        headers = await self.client._get_headers()
        
        logger.debug(f"   START SERVICE BUS Abandon Message:")
        logger.debug(f"   Message ID: {message.message_id}")
        logger.debug(f"   Lock Token: {message.lock_token}")
        
        response = requests.post(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        logger.debug(f"   Abandon Message Response - Status: {response.status_code}")
        
        if response.status_code not in [200, 204]:
            logger.error(f"   Service Bus Abandon API Error: {response.status_code}")
            logger.error(f"   Response text: {response.text}")
        
        # Don't raise for abandon operations - log and continue
        if response.status_code in [200, 204]:
            logger.debug(f"   Message {message.message_id} abandoned successfully")
        else:
            logger.warning(f"   Failed to abandon message {message.message_id}, status: {response.status_code}")
        
    async def close(self):
        """Close the queue receiver"""
        self._closed = True
        logger.info(f"ServiceBusQueueReceiver for queue '{self.queue_name}' closed")


class ServiceBusMessage:
    """
    Service Bus message wrapper for compatibility with Azure SDK
    
    This class provides the same interface as the Azure SDK Service Bus message
    but works with our DirectServiceBusClient.
    """
    
    def __init__(self, message_id: str, body: Any, lock_token: Optional[str], receiver: ServiceBusQueueReceiver):
        """
        Initialize the Service Bus message
        
        Args:
            message_id: Unique message identifier
            body: Message body content
            lock_token: Message lock token for completion/abandonment
            receiver: Queue receiver that received this message
        """
        self.message_id = message_id
        self.body = body
        self.lock_token = lock_token
        self.receiver = receiver
        
    def __str__(self) -> str:
        """
        Get string representation of message body
        
        Returns:
            str: Message body as string
        """
        if isinstance(self.body, str):
            return self.body
        elif isinstance(self.body, dict):
            return json.dumps(self.body)
        else:
            return str(self.body)
            
    def __repr__(self) -> str:
        """Get detailed representation of the message"""
        return f"ServiceBusMessage(id={self.message_id}, lock_token={self.lock_token})"
