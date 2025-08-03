"""
Simple JWT validator that just decodes tokens without signature verification
"""
import jwt
from typing import Dict, Any

class AzureTokenValidator:
    """
    Azure JWT token validator class for validating Bearer tokens
    
    This class provides token validation functionality without signature verification,
    focusing on extracting user information and validating tenant ID.
    """
    
    def __init__(self, expected_tenant_id: str):
        """
        Initialize the token validator
        
        Args:
            expected_tenant_id: The expected Azure tenant ID for validation
        """
        self.expected_tenant_id = expected_tenant_id
    
    def validate_token(self, authorization_header: str) -> Dict[str, Any]:
        """
        Validate Bearer token and extract user information
        
        Args:
            authorization_header: The Authorization header containing Bearer token
            
        Returns:
            Dict[str, Any]: User information extracted from token
            
        Raises:
            ValueError: If token validation fails
        """
        return validate_bearer_token(authorization_header, self.expected_tenant_id)

def validate_bearer_token(authorization_header: str, expected_tenant_id: str) -> Dict[str, Any]:
    """
    Simple JWT token decode without signature validation
    Just extract user info from the token payload
    """
    if not authorization_header:
        raise ValueError("Missing Authorization header")
        
    if not authorization_header.startswith('Bearer '):
        raise ValueError("Invalid Authorization header format. Must start with 'Bearer '")
        
    token = authorization_header[7:]  # Remove "Bearer " prefix
    
    try:
        # Decode without verification to get payload
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # Extract tenant ID from token and validate
        token_tenant = payload.get('tid')
        if token_tenant != expected_tenant_id:
            raise ValueError(f"Token tenant {token_tenant} doesn't match expected {expected_tenant_id}")
        
        # Return user info
        return {
            'user_id': payload.get('oid'),
            'username': payload.get('unique_name') or payload.get('upn') or payload.get('preferred_username'),
            'tenant_id': payload.get('tid'),
            'app_id': payload.get('appid'),
        }
    except Exception as e:
        raise ValueError(f"Token decode failed: {e}")
