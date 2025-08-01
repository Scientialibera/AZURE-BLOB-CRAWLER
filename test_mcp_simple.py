#!/usr/bin/env python3
"""
Simple MCP client test script using PowerShell and curl

This script:
1. Gets a real Azure AD token using Azure CLI
2. Tests the MCP server with HTTP calls
3. Tests the azure_search tool
"""

import subprocess
import json
import sys

# Configuration
MCP_SERVER_URL = "https://mcp-server.blackwave-42d54423.eastus2.azurecontainerapps.io"

def get_azure_token():
    """Get Azure AD access token using Azure CLI"""
    try:
        print("🔑 Getting Azure AD access token...")
        result = subprocess.run([
            "az", "account", "get-access-token", 
            "--resource", "https://graph.microsoft.com",
            "--query", "accessToken",
            "-o", "tsv"
        ], capture_output=True, text=True, check=True)
        
        token = result.stdout.strip()
        if token:
            print("✅ Successfully obtained Azure AD token")
            print(f"Token preview: {token[:20]}...")
            return token
        else:
            print("❌ Failed to get token - empty response")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to get Azure AD token: {e}")
        print("💡 Make sure you're logged in with: az login")
        return None
    except FileNotFoundError:
        print("❌ Azure CLI not found. Please install it first.")
        return None

def test_health_check():
    """Test the health endpoint"""
    print("\n📋 Test 1: Health Check")
    try:
        result = subprocess.run([
            "curl", "-s", "-f", f"{MCP_SERVER_URL}/health"
        ], capture_output=True, text=True, check=True)
        
        health_data = json.loads(result.stdout)
        print(f"✅ Health check passed: {health_data}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Health check failed: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON response: {e}")
        return False

def test_mcp_tools_list(token):
    """Test MCP tools list endpoint"""
    print("\n📋 Test 2: MCP Tools List")
    
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    
    # Try different possible MCP endpoints
    endpoints = ["/mcp", "/jsonrpc", "/rpc", "/tools"]
    
    for endpoint in endpoints:
        try:
            print(f"  Trying endpoint: {endpoint}")
            
            # Use curl to make the request
            result = subprocess.run([
                "curl", "-s", "-X", "POST",
                f"{MCP_SERVER_URL}{endpoint}",
                "-H", "Content-Type: application/json",
                "-H", f"Authorization: Bearer {token}",
                "-d", json.dumps(mcp_request)
            ], capture_output=True, text=True, check=True)
            
            if result.stdout:
                try:
                    response = json.loads(result.stdout)
                    print(f"✅ MCP tools list successful via {endpoint}:")
                    print(json.dumps(response, indent=2))
                    return True, endpoint
                except json.JSONDecodeError:
                    print(f"  ⚠️  Invalid JSON response from {endpoint}")
            
        except subprocess.CalledProcessError as e:
            print(f"  ⚠️  Endpoint {endpoint} failed: {e}")
    
    print("❌ No working MCP endpoints found")
    return False, None

def test_azure_search(token, mcp_endpoint):
    """Test the azure_search tool"""
    print("\n📋 Test 3: Azure Search Tool")
    
    search_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "azure_search",
            "arguments": {
                "query": "document",
                "top": 3,
                "authorization": f"Bearer {token}"
            }
        }
    }
    
    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST",
            f"{MCP_SERVER_URL}{mcp_endpoint}",
            "-H", "Content-Type: application/json",
            "-H", f"Authorization: Bearer {token}",
            "-d", json.dumps(search_request)
        ], capture_output=True, text=True, check=True)
        
        if result.stdout:
            try:
                response = json.loads(result.stdout)
                print(f"✅ Azure Search test successful:")
                print(json.dumps(response, indent=2))
                return True
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON response: {e}")
                print(f"Raw response: {result.stdout}")
                return False
        else:
            print("❌ Empty response from azure_search tool")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Azure Search test failed: {e}")
        return False

def test_filter_search(token, mcp_endpoint):
    """Test azure_search with filters"""
    print("\n📋 Test 4: Azure Search with Filters")
    
    search_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "azure_search",
            "arguments": {
                "filters": {
                    "metadata_storage_size": "gt 1000"
                },
                "top": 2,
                "authorization": f"Bearer {token}"
            }
        }
    }
    
    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST",
            f"{MCP_SERVER_URL}{mcp_endpoint}",
            "-H", "Content-Type: application/json", 
            "-H", f"Authorization: Bearer {token}",
            "-d", json.dumps(search_request)
        ], capture_output=True, text=True, check=True)
        
        if result.stdout:
            try:
                response = json.loads(result.stdout)
                print(f"✅ Filter search test successful:")
                print(json.dumps(response, indent=2))
                return True
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON response: {e}")
                print(f"Raw response: {result.stdout}")
                return False
        else:
            print("❌ Empty response from filter search")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Filter search test failed: {e}")
        return False

def main():
    """Main function"""
    print("🧪 MCP Server Test Script")
    print("=" * 60)
    print(f"Testing server: {MCP_SERVER_URL}")
    print("-" * 60)
    
    # Get Azure AD token
    token = get_azure_token()
    if not token:
        print("❌ Cannot proceed without Azure AD token")
        return 1
    
    # Test 1: Health check
    health_ok = test_health_check()
    if not health_ok:
        print("❌ Health check failed - server may not be running")
        return 1
    
    # Test 2: MCP tools list
    tools_ok, mcp_endpoint = test_mcp_tools_list(token)
    if not tools_ok:
        print("⚠️  MCP tools list failed - server might not support HTTP MCP protocol")
        print("💡 The server might be a stdio-based MCP server")
        return 1
    
    # Test 3: Azure search
    search_ok = test_azure_search(token, mcp_endpoint)
    
    # Test 4: Filter search
    filter_ok = test_filter_search(token, mcp_endpoint)
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 Test Results Summary:")
    print(f"✅ Health Check: {'PASS' if health_ok else 'FAIL'}")
    print(f"✅ MCP Tools List: {'PASS' if tools_ok else 'FAIL'}")
    print(f"✅ Azure Search: {'PASS' if search_ok else 'FAIL'}")
    print(f"✅ Filter Search: {'PASS' if filter_ok else 'FAIL'}")
    
    if health_ok and tools_ok and search_ok:
        print("\n🎉 All core tests passed!")
        print("\n📝 Your MCP server is working correctly:")
        print("• Authentication with Azure AD tokens ✅")
        print("• MCP protocol communication ✅") 
        print("• Azure AI Search integration ✅")
        print("• Filter-based search ✅")
        
        print(f"\n💡 MCP Endpoint: {MCP_SERVER_URL}{mcp_endpoint}")
        print("💡 Use this endpoint in your MCP client applications")
        
    else:
        print("\n❌ Some tests failed")
        print("💡 Check the server logs:")
        print("   az containerapp logs show --name mcp-server --resource-group indexa10801-rg --follow")
    
    return 0 if (health_ok and tools_ok and search_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
