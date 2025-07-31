"""
JWT Authentication module for MCP Search Service

This module provides JWT token validation for Azure AD tokens.
"""

import logging
import jwt
import requests
from typing import Optional, Dict, Any
from functools import lru_cache

from config.settings import (
    AZURE_TENANT_ID, JWT_ISSUER, JWT_AUDIENCE, JWT_ALGORITHM
)

logger = logging.getLogger(__name__)


class JWTAuthenticator:
    """
    JWT token authenticator for Azure AD tokens
    
    This class validates JWT tokens issued by Azure AD and extracts
    user information for authorization decisions.
    """
    
    def __init__(self):
        """Initialize the JWT authenticator"""
        self.tenant_id = AZURE_TENANT_ID
        self.issuer = JWT_ISSUER
        self.audience = JWT_AUDIENCE
        self.algorithm = JWT_ALGORITHM
        self._jwks_uri = f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"
        
    @lru_cache(maxsize=1)
    def _get_jwks(self) -> Dict[str, Any]:
        """
        Get JSON Web Key Set (JWKS) from Azure AD
        
        Returns:
            Dict[str, Any]: JWKS data for token signature validation
            
        Raises:
            Exception: If JWKS retrieval fails
        """
        try:
            response = requests.get(self._jwks_uri, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to retrieve JWKS: {e}")
            raise Exception(f"Could not retrieve token validation keys: {e}")
    
    def _get_signing_key(self, token_header: Dict[str, Any]) -> str:
        """
        Get the signing key for token validation
        
        Args:
            token_header: JWT token header containing key ID
            
        Returns:
            str: Public key for signature validation
            
        Raises:
            Exception: If signing key not found
        """
        kid = token_header.get('kid')
        if not kid:
            raise Exception("Token missing key ID (kid)")
        
        jwks = self._get_jwks()
        
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                # Convert JWK to PEM format for PyJWT
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        
        raise Exception(f"Signing key not found for kid: {kid}")
    
    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a JWT token and extract claims
        
        Args:
            token: JWT token string
            
        Returns:
            Optional[Dict[str, Any]]: Token claims if valid, None if invalid
        """
        try:
            # Decode token header to get key ID
            header = jwt.get_unverified_header(token)
            
            # Get signing key
            signing_key = self._get_signing_key(header)
            
            # Validate and decode token
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True
                }
            )
            
            logger.info(f"Token validation successful for user: {claims.get('upn', 'unknown')}")
            return claims
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: Token has expired")
            return None
        except jwt.InvalidAudienceError:
            logger.warning("Token validation failed: Invalid audience")
            return None
        except jwt.InvalidIssuerError:
            logger.warning("Token validation failed: Invalid issuer")
            return None
        except jwt.InvalidSignatureError:
            logger.warning("Token validation failed: Invalid signature")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: Invalid token - {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    def extract_user_info(self, claims: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract user information from token claims
        
        Args:
            claims: JWT token claims
            
        Returns:
            Dict[str, Any]: User information
        """
        return {
            'user_id': claims.get('oid'),  # Object ID
            'username': claims.get('upn') or claims.get('preferred_username'),  # User Principal Name
            'name': claims.get('name'),
            'email': claims.get('email'),
            'tenant_id': claims.get('tid'),
            'app_id': claims.get('appid'),
            'roles': claims.get('roles', []),
            'scopes': claims.get('scp', '').split() if claims.get('scp') else []
        }


def create_jwt_authenticator() -> Optional[JWTAuthenticator]:
    """
    Factory function to create JWT authenticator
    
    Returns:
        Optional[JWTAuthenticator]: Authenticator instance or None if not configured
    """
    if not AZURE_TENANT_ID:
        logger.warning("JWT authentication not configured - AZURE_TENANT_ID missing")
        return None
    
    return JWTAuthenticator()
