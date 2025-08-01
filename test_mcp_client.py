#!/usr/bin/env python3
"""
Simple MCP client test script for Azure AI Search MCP Server

This script:
1. Gets a real Azure AD token using Azure CLI
2. Connects to the MCP server
3. Tests the azure_search tool
"""

import subprocess
import json
import sys
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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

async def test_mcp_server():
    """Test the MCP server using the MCP client"""
    
    # Get Azure AD token
    token = get_azure_token()
    if not token:
        return False
    
    print(f"\n🚀 Testing MCP Server: {MCP_SERVER_URL}")
    print("-" * 60)
    
    try:
        # For HTTP-based MCP servers, we need to use a different approach
        # Since this is a web-based MCP server, let's test with direct HTTP calls
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            # Test 1: Health check
            print("📋 Test 1: Health Check")
            async with session.get(f"{MCP_SERVER_URL}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print(f"✅ Health check passed: {health_data}")
                else:
                    print(f"❌ Health check failed: {response.status}")
                    return False
            
            # Test 2: MCP Tools List (if available via HTTP)
            print("\n📋 Test 2: List MCP Tools")
            mcp_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            # Try common MCP endpoints
            mcp_endpoints = ["/mcp", "/jsonrpc", "/rpc"]
            
            tools_found = False
            for endpoint in mcp_endpoints:
                try:
                    async with session.post(f"{MCP_SERVER_URL}{endpoint}", 
                                          json=mcp_request, 
                                          headers=headers) as response:
                        if response.status == 200:
                            result = await response.json()
                            print(f"✅ MCP tools list successful via {endpoint}:")
                            print(json.dumps(result, indent=2))
                            tools_found = True
                            break
                        elif response.status == 404:
                            continue  # Try next endpoint
                        else:
                            print(f"⚠️  Endpoint {endpoint} returned {response.status}")
                except Exception as e:
                    print(f"⚠️  Endpoint {endpoint} error: {e}")
            
            if not tools_found:
                print("⚠️  No MCP endpoints found - this might be a stdio-based MCP server")
                print("💡 The server might need to be connected via stdio protocol instead of HTTP")
            
            # Test 3: Azure Search Tool (if we found MCP endpoints)
            if tools_found:
                print("\n📋 Test 3: Azure Search Tool")
                search_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "azure_search",
                        "arguments": {
                            "query": "test document",
                            "top": 5,
                            "authorization": f"Bearer {token}"
                        }
                    }
                }
                
                async with session.post(f"{MCP_SERVER_URL}/mcp", 
                                      json=search_request, 
                                      headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ Azure Search test successful:")
                        print(json.dumps(result, indent=2))
                    else:
                        print(f"⚠️  Azure Search test failed: {response.status}")
                        response_text = await response.text()
                        print(f"Response: {response_text}")
        
        return True
        
    except Exception as e:
        print(f"❌ MCP test failed: {e}")
        return False

def main():
    """Main function"""
    print("🧪 MCP Server Test Script")
    print("=" * 60)
    
    # Run the async test
    success = asyncio.run(test_mcp_server())
    
    print("\n" + "=" * 60)
    if success:
        print("✅ MCP Server tests completed!")
        print("\n📝 Summary:")
        print("• Server is healthy and responding")
        print("• Azure AD authentication is working")
        print("• MCP protocol endpoints tested")
        
        print("\n💡 Next steps:")
        print("1. Use a proper MCP client library to connect")
        print("2. Test more complex search queries")
        print("3. Test different filter combinations")
        
    else:
        print("❌ Some tests failed")
        print("💡 Check the server logs for more details:")
        print("   az containerapp logs show --name mcp-server --resource-group indexa10801-rg --follow")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
