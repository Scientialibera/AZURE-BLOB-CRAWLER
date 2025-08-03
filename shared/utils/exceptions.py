"""
Custom exceptions for the document processing pipeline

This module defines custom exceptions to handle specific error conditions
in the document processing workflow.
"""


class BlobNotFoundError(Exception):
    """
    Exception raised when a blob is not found in Azure Storage
    
    This is a specific case where the message should be marked as processed
    rather than failed, since retrying won't help if the blob doesn't exist.
    """
    
    def __init__(self, blob_name: str, container_name: str, message: str = None):
        """
        Initialize the BlobNotFoundError
        
        Args:
            blob_name: Name of the blob that was not found
            container_name: Name of the container where the blob was expected
            message: Optional custom error message
        """
        self.blob_name = blob_name
        self.container_name = container_name
        
        if message is None:
            message = f"Blob '{blob_name}' not found in container '{container_name}'"
        
        super().__init__(message)


class ProcessingSkippedError(Exception):
    """
    Exception raised when processing is intentionally skipped
    
    This indicates that the processing was skipped for a valid reason
    (e.g., unsupported file type, file too large, etc.) and the message
    should be marked as processed rather than failed.
    """
    
    def __init__(self, reason: str, blob_name: str = None):
        """
        Initialize the ProcessingSkippedError
        
        Args:
            reason: Reason why processing was skipped
            blob_name: Optional blob name that was skipped
        """
        self.reason = reason
        self.blob_name = blob_name
        
        if blob_name:
            message = f"Processing skipped for '{blob_name}': {reason}"
        else:
            message = f"Processing skipped: {reason}"
        
        super().__init__(message)


class TokenAcquisitionError(Exception):
    """
    Exception raised when token acquisition fails
    
    This indicates that the Azure managed identity or credential system
    failed to acquire a token, which may require retry or different handling.
    """
    
    def __init__(self, scope: str, reason: str = None):
        """
        Initialize the TokenAcquisitionError
        
        Args:
            scope: The token scope that failed to acquire
            reason: Optional reason for the failure
        """
        self.scope = scope
        self.reason = reason
        
        if reason:
            message = f"Token acquisition failed for scope '{scope}': {reason}"
        else:
            message = f"Token acquisition failed for scope '{scope}'"
        
        super().__init__(message)
