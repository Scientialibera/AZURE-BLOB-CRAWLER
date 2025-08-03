"""
Simple JWT validator that just decodes tokens without signature verification
"""
import jwt
from typing import Dict, Any

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
