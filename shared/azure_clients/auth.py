"""
Azure authentication and token management

This module provides base classes and utilities for managing Azure authentication
with managed identity and token caching.
"""

import logging
import threading
import pytz
import asyncio
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Optional

from azure.identity.aio import DefaultAzureCredential

from utils.exceptions import TokenAcquisitionError

from config.settings import (
    TOKEN_LF, TOKEN_PREVIEW_LENGTH, DEFAULT_TIMEZONE, TOKEN_ACQUISITION_TIMEOUT_SECONDS,
    HTTP_CONTENT_TYPE_JSON, HTTP_AUTH_BEARER_PREFIX, AZURE_CLIENT_ID, VERBOSE_AUTH_LOGGING
)

logger = logging.getLogger(__name__)


async def get_token_async(credential, scope: str) -> Optional[str]:
    """
    Get Azure access token using DefaultAzureCredential with timeout protection
    
    Args:
        credential: Azure credential instance
        scope: The token scope to request
        
    Returns:
        Optional[str]: Access token or None if failed
    """
    try:
        if VERBOSE_AUTH_LOGGING:
            logger.info(f"   Requesting token for scope: {scope}")
        
        # Add timeout protection around token acquisition
        try:
            # Use asyncio.wait_for to add a timeout to the token acquisition
            token = await asyncio.wait_for(
                credential.get_token(scope), 
                timeout=TOKEN_ACQUISITION_TIMEOUT_SECONDS
            )
            if VERBOSE_AUTH_LOGGING:
                logger.info(f"   Token acquired successfully - Expires: {datetime.fromtimestamp(token.expires_on, tz=timezone.utc)}")
                logger.info(f"   Token preview: {token.token[:TOKEN_PREVIEW_LENGTH]}...")
            return token.token
            
        except asyncio.TimeoutError:
            logger.error(f"   Token acquisition timed out after {TOKEN_ACQUISITION_TIMEOUT_SECONDS} seconds for scope {scope}")
            raise TokenAcquisitionError(scope, f"Timeout after {TOKEN_ACQUISITION_TIMEOUT_SECONDS} seconds")
            
    except Exception as e:
        logger.error(f"   Failed to get token for scope {scope}: {e}")
        raise TokenAcquisitionError(scope, str(e))


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
        if VERBOSE_AUTH_LOGGING:
            logger.info(f"[Thread {thread_id}] checking token at {now_est}")

        if self.token and now < self.token_expiry:
            if VERBOSE_AUTH_LOGGING:
                token_expiry_est = self.token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                logger.info(f"[Thread {thread_id}] Reusing existing Azure token. Valid until {token_expiry_est.isoformat()}.")
            return  # Token is still valid; no need to refresh

        with self._lock:
            now = datetime.now(timezone.utc)
            if self.token and now < self.token_expiry:
                if VERBOSE_AUTH_LOGGING:
                    token_expiry_est = self.token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                    logger.info(f"[Thread {thread_id}] Token was refreshed by another thread. Reusing existing token. Valid until {token_expiry_est.isoformat()}.")
                return

            if VERBOSE_AUTH_LOGGING:
                logger.info(f"[Thread {thread_id}] Refreshing Azure token.")
            try:
                new_token = await get_token_async(self.credential, self.scope)
                self.token = new_token
                self.token_expiry = now + timedelta(minutes=TOKEN_LF)  # Adjust based on token TTL
                if VERBOSE_AUTH_LOGGING:
                    token_expiry_est = self.token_expiry.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                    logger.info(f"[Thread {thread_id}] New token acquired. Valid until {token_expiry_est.isoformat()}.")
            except TokenAcquisitionError as e:
                logger.error(f"[Thread {thread_id}] Failed to acquire token: {e}")
                raise Exception(f"Failed to acquire a new token for scope {self.scope}: {e}")
    
    async def pre_warm_token(self) -> bool:
        """
        Pre-warm the token by acquiring it during initialization
        
        Returns:
            bool: True if token was successfully pre-warmed, False otherwise
        """
        try:
            if VERBOSE_AUTH_LOGGING:
                logger.info(f"Pre-warming token for scope: {self.scope}")
            await self._refresh_token()
            if VERBOSE_AUTH_LOGGING:
                logger.info(f"Token pre-warming successful for scope: {self.scope}")
            return True
        except Exception as e:
            logger.error(f"Token pre-warming failed for scope {self.scope}: {e}")
            return False
 
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
    try:
        logger.info(f"Creating DefaultAzureCredential with client ID: {AZURE_CLIENT_ID}")
        
        # Create credential with explicit configuration
        credential = DefaultAzureCredential(
            managed_identity_client_id=AZURE_CLIENT_ID,  # optional
            exclude_interactive_browser_credential=True,  # Exclude interactive auth in container
            exclude_visual_studio_code_credential=True,   # Exclude VS Code auth in container
            exclude_azure_cli_credential=True,            # Exclude CLI auth in container
            exclude_environment_credential=False,         # Keep environment credential
            exclude_managed_identity_credential=False,    # Keep managed identity credential
        )
        
        logger.info("DefaultAzureCredential created successfully")
        return credential
        
    except Exception as e:
        logger.error(f"Failed to create DefaultAzureCredential: {e}")
        raise
