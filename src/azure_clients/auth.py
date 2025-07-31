"""
Azure authentication and token management

This module provides base classes and utilities for managing Azure authentication
with managed identity and token caching.
"""

import logging
import threading
import pytz
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Optional

from azure.identity.aio import DefaultAzureCredential

from config.settings import (
    TOKEN_LF, TOKEN_PREVIEW_LENGTH, DEFAULT_TIMEZONE, 
    HTTP_CONTENT_TYPE_JSON, HTTP_AUTH_BEARER_PREFIX, AZURE_CLIENT_ID
)

logger = logging.getLogger(__name__)


async def get_token_async(credential, scope: str) -> Optional[str]:
    """
    Get Azure access token using DefaultAzureCredential
    
    Args:
        credential: Azure credential instance
        scope: The token scope to request
        
    Returns:
        Optional[str]: Access token or None if failed
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
    
    This class provides common functionality for Azure clients that need to manage
    access tokens with automatic refresh and thread-safe caching.
    """
    
    def __init__(self, credential, scope: str):
        """
        Initialize the Azure client base
        
        Args:
            credential: Azure credential instance
            scope: The token scope for this client
        """
        self.credential = credential
        self.scope = scope
        self.token: Optional[str] = None
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
 
    async def _get_headers(self) -> dict:
        """
        Prepare headers with the current token.
        
        Returns:
            dict: HTTP headers with authorization
        """
        await self._refresh_token()
        return {
            "Content-Type": HTTP_CONTENT_TYPE_JSON, 
            "Authorization": f"{HTTP_AUTH_BEARER_PREFIX} {self.token}"
        }


def create_credential() -> DefaultAzureCredential:
    """
    Create Azure credential with proper configuration
    
    Returns:
        DefaultAzureCredential: Configured credential instance
    """
    logger.info(f"Using DefaultAzureCredential with client ID: {AZURE_CLIENT_ID}")
    return DefaultAzureCredential(
        managed_identity_client_id=AZURE_CLIENT_ID   # optional
    )
