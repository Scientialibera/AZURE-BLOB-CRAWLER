"""
Test script for the Azure Search MCP Server

This script demonstrates how to call the MCP server with search requests
including JWT token authentication.
"""

import asyncio
import json
import requests
from typing import Dict, Any

# Example usage configuration
MCP_SERVER_URL = "http://localhost:8080"
EXAMPLE_BEARER_TOKEN = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6..."  # Replace with actual token


def test_search_with_query():
    """Test search with text query and filters"""
    search_request = {
        "query": "artificial intelligence",
        "filters": {
            "category": "eq 'technology'",
            "publishedDate": "ge 2023-01-01"
        },
        "top": 5,
        "authorization": EXAMPLE_BEARER_TOKEN
    }
    
    print("=== Search with Query Example ===")
    print(f"Request: {json.dumps(search_request, indent=2)}")
    print()


def test_filter_only_search():
    """Test filter-only search (no text query)"""
    search_request = {
        "filters": {
            "status": "eq 'published'",
            "author": "eq 'John Doe'"
        },
        "top": 10,
        "select_fields": ["id", "title", "content", "author", "publishedDate"],
        "authorization": EXAMPLE_BEARER_TOKEN
    }
    
    print("=== Filter-Only Search Example ===")
    print(f"Request: {json.dumps(search_request, indent=2)}")
    print()


def test_health_check():
    """Test health check endpoint"""
    try:
        response = requests.get(f"{MCP_SERVER_URL}/health", timeout=5)
        print("=== Health Check ===")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print()
    except requests.RequestException as e:
        print(f"Health check failed: {e}")


async def example_mcp_call():
    """Example of how the MCP server would be called"""
    
    # This is pseudo-code showing how an MCP client would call the server
    example_call = {
        "method": "tools/call",
        "params": {
            "name": "azure_search",
            "arguments": {
                "query": "machine learning algorithms",
                "filters": {
                    "difficulty": "eq 'intermediate'",
                    "tags": "search.in('python,ai,ml')"
                },
                "top": 15,
                "select_fields": ["id", "title", "summary", "tags", "score"],
                "authorization": EXAMPLE_BEARER_TOKEN
            }
        }
    }
    
    print("=== Example MCP Tool Call ===")
    print(json.dumps(example_call, indent=2))
    print()


def print_azure_search_filter_examples():
    """Print examples of Azure Search filter expressions"""
    
    print("=== Azure Search Filter Expression Examples ===")
    print()
    
    examples = {
        "Exact match": "eq 'value'",
        "Not equal": "ne 'value'",
        "Greater than": "gt 100",
        "Greater than or equal": "ge 50",
        "Less than": "lt 1000",
        "Less than or equal": "le 500",
        "In list": "search.in('value1,value2,value3')",
        "Contains text": "search.ismatch('keyword')",
        "Date range": "ge 2023-01-01 and le 2023-12-31",
        "Multiple conditions": "eq 'published' and ge 2023-01-01",
        "Null check": "eq null",
        "Not null check": "ne null"
    }
    
    for description, expression in examples.items():
        print(f"{description:20}: {expression}")
    
    print()
    print("Note: These expressions should be used as values in the filters dictionary.")
    print("Example: {'status': \"eq 'published'\", 'score': 'ge 80'}")
    print()


def main():
    """Main test function"""
    print("Azure Search MCP Server - Test Examples")
    print("=" * 50)
    print()
    
    # Show configuration examples
    test_search_with_query()
    test_filter_only_search()
    
    # Show MCP call example
    asyncio.run(example_mcp_call())
    
    # Show filter examples
    print_azure_search_filter_examples()
    
    # Test health endpoint if server is running
    print("Testing health check (if server is running)...")
    test_health_check()
    
    print("=" * 50)
    print("To use this MCP server:")
    print("1. Deploy infrastructure: ./scripts/deploy-infrastructure.ps1")
    print("2. Build and deploy MCP server: ./scripts/deploy-mcp.ps1")
    print("3. Get a valid Azure JWT token")
    print("4. Call the azure_search tool with your token and search parameters")
    print()
    print("The server will validate your token against the configured tenant ID")
    print("and return search results with vector fields excluded.")


if __name__ == "__main__":
    main()
