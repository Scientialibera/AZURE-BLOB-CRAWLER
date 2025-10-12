"""
Basic import tests to verify dependencies and module structure
"""
import pytest
import sys
import os

# Add shared directory to path for testing
shared_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'shared')
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)


def test_import_mcp_dependencies():
    """Test that MCP dependencies are available"""
    import mcp
    from fastmcp import FastMCP
    assert FastMCP is not None


def test_import_azure_clients():
    """Test that azure_clients module imports correctly"""
    from shared.azure_clients import create_credential
    assert create_credential is not None


def test_import_config():
    """Test that config module imports correctly"""
    from shared.config.settings import MCP_SERVER_NAME, MCP_PORT
    assert MCP_SERVER_NAME is not None
    assert MCP_PORT > 0


def test_import_jwt_validation():
    """Test that JWT validation dependencies are available"""
    import jwt
    from shared.auth.jwt_validator import JWTValidator
    assert JWTValidator is not None


def test_import_search_client():
    """Test that search client imports correctly"""
    from shared.azure_clients.search_client import DirectSearchClient
    assert DirectSearchClient is not None