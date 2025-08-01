"""
JWT Token Validation for Azure Authentication

This module provides JWT token validation for Azure tokens to ensure
requests are properly authenticated with the correct tenant.
"""

import jwt
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AzureTokenValidator:
    """
    Validates Azure JWT tokens and verifies tenant ID
    """
    
    def __init__(self, tenant_id: str):
        """
        Initialize the token validator
        
        Args:
            tenant_id: Expected Azure tenant ID
        """
        self.tenant_id = tenant_id
        self.expected_issuer = f"https://sts.windows.net/{tenant_id}/"
        self._jwks_cache = {}
        
    def _get_jwks_uri(self, issuer: str) -> str:
        """Get JWKS URI from the issuer's OpenID configuration"""
        if issuer.endswith('/'):
            issuer = issuer[:-1]
        return f"{issuer}/.well-known/openid_configuration"
    
    def _fetch_signing_keys(self, issuer: str) -> Dict[str, Any]:
        """
        Fetch JWT signing keys from Azure's JWKS endpoint
        
        Args:
            issuer: Token issuer URL
            
        Returns:
            Dict containing the signing keys
        """
        if issuer in self._jwks_cache:
            return self._jwks_cache[issuer]
            
        try:
            # Get OpenID configuration
            config_url = self._get_jwks_uri(issuer)
            config_response = requests.get(config_url, timeout=10)
            config_response.raise_for_status()
            config = config_response.json()
            
            # Get JWKS
            jwks_url = config['jwks_uri']
            jwks_response = requests.get(jwks_url, timeout=10)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()
            
            # Cache the keys
            self._jwks_cache[issuer] = jwks
            return jwks
            
        except Exception as e:
            logger.error(f"Failed to fetch signing keys from {issuer}: {e}")
            raise ValueError(f"Unable to fetch signing keys: {e}")
    
    def _get_signing_key(self, token_header: Dict[str, Any], issuer: str) -> str:
        """
        Get the signing key for token validation
        
        Args:
            token_header: JWT token header
            issuer: Token issuer
            
        Returns:
            The signing key
        """
        jwks = self._fetch_signing_keys(issuer)
        
        # Find the key with matching kid
        kid = token_header.get('kid')
        if not kid:
            raise ValueError("Token header missing 'kid' field")
            
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                # Convert JWK to PEM format
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
                
        raise ValueError(f"Unable to find signing key with kid: {kid}")
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate Azure JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Dict containing the decoded token payload
            
        Raises:
            ValueError: If token validation fails
        """
        try:
            # Decode token header without verification to get issuer and kid
            unverified_header = jwt.get_unverified_header(token)
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            
            # Check issuer matches expected tenant
            issuer = unverified_payload.get('iss')
            if not issuer:
                raise ValueError("Token missing 'iss' (issuer) claim")
                
            if issuer != self.expected_issuer:
                raise ValueError(f"Invalid issuer. Expected: {self.expected_issuer}, Got: {issuer}")
            
            # Get signing key
            signing_key = self._get_signing_key(unverified_header, issuer)
            
            # Verify and decode token
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=['RS256'],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": False,  # We'll validate audience separately if needed
                }
            )
            
            # Additional validation
            now = datetime.now(timezone.utc).timestamp()
            
            # Check expiration
            exp = payload.get('exp')
            if exp and exp < now:
                raise ValueError("Token has expired")
                
            # Check not before
            nbf = payload.get('nbf')
            if nbf and nbf > now:
                raise ValueError("Token not yet valid")
            
            logger.info(f"Token validated successfully for tenant: {self.tenant_id}")
            return payload
            
        except jwt.InvalidTokenError as e:
            logger.error(f"JWT validation failed: {e}")
            raise ValueError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise ValueError(f"Token validation failed: {e}")
    
    def extract_user_info(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract user information from validated token payload
        
        Args:
            payload: Validated JWT payload
            
        Returns:
            Dict containing user information
        """
        return {
            'user_id': payload.get('oid'),  # Object ID
            'username': payload.get('unique_name') or payload.get('upn'),
            'app_id': payload.get('appid'),
            'tenant_id': payload.get('tid'),
            'audience': payload.get('aud'),
            'issuer': payload.get('iss'),
            'scopes': payload.get('scp', '').split() if payload.get('scp') else [],
            'roles': payload.get('roles', []),
        }


def validate_bearer_token(authorization_header: str, tenant_id: str) -> Dict[str, Any]:
    """
    Convenience function to validate Bearer token from Authorization header
    
    Args:
        authorization_header: Authorization header value (e.g., "Bearer <token>")
        tenant_id: Expected Azure tenant ID
        
    Returns:
        Dict containing user information from validated token
        
    Raises:
        ValueError: If token validation fails
    """
    if not authorization_header:
        raise ValueError("Missing Authorization header")
        
    if not authorization_header.startswith('Bearer '):
        raise ValueError("Invalid Authorization header format. Must start with 'Bearer '")
        
    token = authorization_header[7:]  # Remove "Bearer " prefix
    
    validator = AzureTokenValidator(tenant_id)
    payload = validator.validate_token(token)
    return validator.extract_user_info(payload)
