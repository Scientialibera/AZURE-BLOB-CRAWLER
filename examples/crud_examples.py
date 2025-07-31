"""
Example usage of enhanced Azure clients with full CRUD operations

This file demonstrates how to use the DirectBlobClient and DirectSearchClient
for comprehensive Create, Read, Update, Delete operations.
"""

import asyncio
import logging
from typing import Dict, Any, List

from azure_clients.auth import create_credential
from azure_clients.blob_client import DirectBlobClient
from azure_clients.search_client import DirectSearchClient
from config.settings import (
    STORAGE_ACCOUNT_NAME, SEARCH_SERVICE_NAME, SEARCH_INDEX_NAME,
    AZURE_STORAGE_SCOPE, AZURE_SEARCH_SCOPE, BLOB_ENDPOINT_SUFFIX, SEARCH_ENDPOINT_SUFFIX
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def blob_crud_examples():
    """
    Demonstrate CRUD operations with Azure Blob Storage
    """
    logger.info("=== BLOB STORAGE CRUD EXAMPLES ===")
    
    # Initialize client
    credential = create_credential()
    account_url = f"https://{STORAGE_ACCOUNT_NAME}{BLOB_ENDPOINT_SUFFIX}"
    blob_client = DirectBlobClient(account_url, credential)
    
    container_name = "test-container"
    blob_name = "test-document.txt"
    
    try:
        # ====== CREATE OPERATIONS ======
        logger.info("\n--- CREATE OPERATIONS ---")
        
        # Create container
        await blob_client.create_container(
            container_name,
            metadata={"purpose": "testing", "created_by": "crud_example"}
        )
        
        # Upload blob
        test_content = "This is a test document for CRUD operations."
        await blob_client.upload_blob(
            container_name, 
            blob_name, 
            test_content,
            content_type="text/plain",
            metadata={"document_type": "test", "version": "1.0"}
        )
        
        # ====== READ OPERATIONS ======
        logger.info("\n--- READ OPERATIONS ---")
        
        # Check if blob exists
        exists = await blob_client.blob_exists(container_name, blob_name)
        logger.info(f"Blob exists: {exists}")
        
        # Get blob properties
        properties = await blob_client.get_blob_properties(container_name, blob_name)
        logger.info(f"Blob size: {properties['size']} bytes")
        logger.info(f"Blob metadata: {properties['metadata']}")
        
        # Download blob
        content = await blob_client.download_blob(container_name, blob_name)
        logger.info(f"Downloaded content: {content.decode('utf-8')}")
        
        # List blobs in container
        blobs = await blob_client.list_blobs(container_name, include_metadata=True)
        logger.info(f"Found {len(blobs)} blobs in container")
        
        # List containers
        containers = await blob_client.list_containers(include_metadata=True)
        logger.info(f"Found {len(containers)} containers")
        
        # ====== UPDATE OPERATIONS ======
        logger.info("\n--- UPDATE OPERATIONS ---")
        
        # Update blob metadata
        new_metadata = {"document_type": "updated_test", "version": "1.1", "last_updated": "2025-01-31"}
        await blob_client.set_blob_metadata(container_name, blob_name, new_metadata)
        
        # Copy blob
        copied_blob_name = "copied-document.txt"
        await blob_client.copy_blob(
            container_name, blob_name,
            container_name, copied_blob_name,
            metadata={"source": blob_name, "copy_type": "example"}
        )
        
        # Upload updated content (overwrite)
        updated_content = "This is the updated content of the test document."
        await blob_client.upload_blob(
            container_name, 
            blob_name, 
            updated_content,
            content_type="text/plain",
            overwrite=True
        )
        
        # ====== DELETE OPERATIONS ======
        logger.info("\n--- DELETE OPERATIONS ---")
        
        # Delete single blob
        await blob_client.delete_blob(container_name, copied_blob_name)
        
        # Delete multiple blobs
        # First create some test blobs
        test_blobs = ["test1.txt", "test2.txt", "test3.txt"]
        for test_blob in test_blobs:
            await blob_client.upload_blob(container_name, test_blob, f"Content for {test_blob}")
        
        # Delete them all
        delete_results = await blob_client.delete_blobs(container_name, test_blobs)
        logger.info(f"Bulk delete results: {delete_results}")
        
        # Clean up - delete the main test blob
        await blob_client.delete_blob(container_name, blob_name)
        
        # Optionally delete the container (DANGEROUS!)
        # await blob_client.delete_container(container_name, confirm=True)
        
    except Exception as e:
        logger.error(f"Error in blob operations: {e}")


async def search_crud_examples():
    """
    Demonstrate CRUD operations with Azure AI Search
    """
    logger.info("\n=== AZURE AI SEARCH CRUD EXAMPLES ===")
    
    # Initialize client
    credential = create_credential()
    endpoint = f"https://{SEARCH_SERVICE_NAME}{SEARCH_ENDPOINT_SUFFIX}"
    search_client = DirectSearchClient(endpoint, credential, AZURE_SEARCH_SCOPE, SEARCH_INDEX_NAME)
    
    try:
        # ====== CREATE OPERATIONS ======
        logger.info("\n--- CREATE OPERATIONS ---")
        
        # Create sample documents
        test_documents = [
            {
                "id": "doc1",
                "content": "This is the first test document for CRUD operations.",
                "title": "Test Document 1",
                "category": "testing",
                "tags": ["test", "crud", "example"]
            },
            {
                "id": "doc2", 
                "content": "This is the second test document with different content.",
                "title": "Test Document 2",
                "category": "testing",
                "tags": ["test", "demo", "example"]
            },
            {
                "id": "doc3",
                "content": "This is the third test document for comprehensive testing.",
                "title": "Test Document 3", 
                "category": "validation",
                "tags": ["test", "validation", "comprehensive"]
            }
        ]
        
        # Upload documents
        await search_client.upload_documents(test_documents)
        
        # Create single document
        single_doc = {
            "id": "doc4",
            "content": "This is a single document created separately.",
            "title": "Single Test Document",
            "category": "individual",
            "tags": ["single", "test"]
        }
        await search_client.create_document(single_doc)
        
        # ====== READ OPERATIONS ======
        logger.info("\n--- READ OPERATIONS ---")
        
        # Search documents
        search_results = await search_client.search_documents(
            query="test document",
            top=10,
            include_total_count=True
        )
        logger.info(f"Search returned {len(search_results['value'])} results")
        
        # Search with filters
        filtered_results = await search_client.search_documents(
            query="*",
            filters="category eq 'testing'",
            select=["id", "title", "category"],
            order_by=["title"]
        )
        logger.info(f"Filtered search returned {len(filtered_results['value'])} results")
        
        # Get specific document
        document = await search_client.get_document("doc1", select=["id", "title", "content"])
        if document:
            logger.info(f"Retrieved document: {document['title']}")
        
        # Count documents
        total_count = await search_client.count_documents()
        logger.info(f"Total documents in index: {total_count}")
        
        # Count with filter
        testing_count = await search_client.count_documents("category eq 'testing'")
        logger.info(f"Documents in testing category: {testing_count}")
        
        # Get index statistics
        stats = await search_client.get_index_statistics()
        logger.info(f"Index statistics: {stats}")
        
        # ====== UPDATE OPERATIONS ======
        logger.info("\n--- UPDATE OPERATIONS ---")
        
        # Update single document
        update_doc = {
            "id": "doc1",
            "title": "Updated Test Document 1",
            "category": "updated",
            "last_modified": "2025-01-31"
        }
        await search_client.update_document(update_doc)
        
        # Update multiple documents
        update_docs = [
            {
                "id": "doc2",
                "category": "updated", 
                "last_modified": "2025-01-31"
            },
            {
                "id": "doc3",
                "category": "updated",
                "last_modified": "2025-01-31"
            }
        ]
        await search_client.update_documents(update_docs)
        
        # Upsert documents (insert or update)
        upsert_docs = [
            {
                "id": "doc5",  # New document
                "content": "This is a new document created via upsert.",
                "title": "Upserted Document",
                "category": "upserted",
                "tags": ["upsert", "new"]
            },
            {
                "id": "doc1",  # Existing document
                "content": "This content was updated via upsert operation.",
                "title": "Upserted Test Document 1"
            }
        ]
        await search_client.upsert_documents(upsert_docs)
        
        # ====== DELETE OPERATIONS ======
        logger.info("\n--- DELETE OPERATIONS ---")
        
        # Delete single document
        await search_client.delete_document("doc4")
        
        # Delete multiple documents by ID
        await search_client.delete_documents(["doc2", "doc3"])
        
        # Delete documents using document objects
        docs_to_delete = [
            {"id": "doc5"}
        ]
        await search_client.delete_documents(docs_to_delete)
        
        # Verify remaining documents
        final_count = await search_client.count_documents()
        logger.info(f"Final document count: {final_count}")
        
        # Clean up - clear entire index (DANGEROUS!)
        # await search_client.clear_index(confirm=True)
        
    except Exception as e:
        logger.error(f"Error in search operations: {e}")


async def compatibility_examples():
    """
    Demonstrate backward compatibility with existing code patterns
    """
    logger.info("\n=== COMPATIBILITY EXAMPLES ===")
    
    # Initialize clients
    credential = create_credential()
    account_url = f"https://{STORAGE_ACCOUNT_NAME}{BLOB_ENDPOINT_SUFFIX}"
    blob_client = DirectBlobClient(account_url, credential)
    
    container_name = "compatibility-test"
    blob_name = "compatibility-test.txt"
    
    try:
        # Create container and blob for testing
        await blob_client.create_container(container_name)
        await blob_client.upload_blob(container_name, blob_name, "Compatibility test content")
        
        # Use wrapper client (maintains existing API)
        blob_wrapper = blob_client.get_blob_client(container_name, blob_name)
        
        # These methods work exactly like the Azure SDK
        properties = await blob_wrapper.get_blob_properties()
        logger.info(f"Blob size (via wrapper): {properties.size} bytes")
        
        download_result = await blob_wrapper.download_blob()
        content = await download_result.readall()
        logger.info(f"Content (via wrapper): {content.decode('utf-8')}")
        
        # Enhanced functionality is also available
        exists = await blob_wrapper.exists()
        logger.info(f"Blob exists (enhanced): {exists}")
        
        # Upload new content
        await blob_wrapper.upload_blob("Updated content via wrapper", overwrite=True)
        
        # Set metadata
        await blob_wrapper.set_blob_metadata({"source": "wrapper", "type": "compatibility_test"})
        
        # Clean up
        await blob_wrapper.delete_blob()
        await blob_client.delete_container(container_name, confirm=True)
        
    except Exception as e:
        logger.error(f"Error in compatibility examples: {e}")


async def main():
    """
    Run all CRUD examples
    """
    logger.info("Starting Azure CRUD Examples")
    
    # Run blob examples
    await blob_crud_examples()
    
    # Run search examples
    await search_crud_examples()
    
    # Run compatibility examples
    await compatibility_examples()
    
    logger.info("All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
