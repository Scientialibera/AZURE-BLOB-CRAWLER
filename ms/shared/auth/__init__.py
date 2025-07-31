"""
Authentication module for Azure File Processing services

This module provides authentication utilities including JWT validation
and managed identity authentication.
"""

from .jwt_auth import JWTAuthenticator, create_jwt_authenticator

__all__ = ['JWTAuthenticator', 'create_jwt_authenticator']
