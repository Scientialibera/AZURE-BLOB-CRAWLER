"""
Utility functions for retry logic and error handling

This module provides decorators and utility functions for handling Azure API rate limits,
transient errors, and implementing retry logic with exponential backoff.
"""

import re
import time
import asyncio
import logging
import functools
from typing import Callable, Any
from inspect import iscoroutinefunction

from config.settings import (
    MAX_RETRIES, RETRY_DELAY_SECONDS, RATE_LIMIT_BASE_WAIT, RATE_LIMIT_MAX_WAIT
)

logger = logging.getLogger(__name__)


def _is_rate_limit_error(error: Exception) -> bool:
    """
    Check if the error is a rate limit error.
    
    Args:
        error: The exception to check
        
    Returns:
        bool: True if it's a rate limit error, False otherwise
    """
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
    """
    Extract wait time from rate limit error or return default.
    
    Args:
        error: The exception to extract wait time from
        
    Returns:
        int: Wait time in seconds
    """
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
        wait_pattern = r'retry after (\d+) seconds?'
        match = re.search(wait_pattern, error_str)
        if match:
            return min(int(match.group(1)), RATE_LIMIT_MAX_WAIT)
        
    except (ValueError, AttributeError):
        pass
    
    # Return default wait time
    return RATE_LIMIT_BASE_WAIT


def retry_logic(max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY_SECONDS) -> Callable:
    """
    Retry decorator for sync and async functions with rate limit handling.
    
    This decorator automatically retries functions that fail due to transient errors,
    with special handling for rate limit errors that don't count against retry attempts.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Base delay between retries in seconds
        
    Returns:
        Callable: Decorated function with retry logic
    """
    
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
