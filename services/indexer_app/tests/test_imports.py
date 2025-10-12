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


def test_import_azure_clients():
    """Test that azure_clients module imports correctly"""
    from shared.azure_clients import create_credential
    assert create_credential is not None


def test_import_config():
    """Test that config module imports correctly"""
    from shared.config.settings import CHUNK_MAX_TOKENS
    assert CHUNK_MAX_TOKENS > 0


def test_import_processing():
    """Test that processing module imports correctly"""
    from shared.processing import DocumentProcessor
    assert DocumentProcessor is not None


def test_import_utils():
    """Test that utils module imports correctly"""
    from shared.utils.chunking import TokenAwareChunker
    assert TokenAwareChunker is not None


def test_supported_file_extensions():
    """Test that file extension constants are defined"""
    from shared.config.settings import ALL_SUPPORTED_EXTENSIONS
    assert len(ALL_SUPPORTED_EXTENSIONS) > 0
    assert 'pdf' in ALL_SUPPORTED_EXTENSIONS
    assert 'docx' in ALL_SUPPORTED_EXTENSIONS
    assert 'txt' in ALL_SUPPORTED_EXTENSIONS