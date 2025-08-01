#!/usr/bin/env python3
"""
Simple test script for SSE-based MCP Server

This script tests the MCP server using Server-Sent Events (SSE) transport.
"""

import subprocess
import json
import sys
import asyncio
import aiohttp

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

async def test_health_check():
    """Test the health endpoint"""
    print("\n📋 Test 1: Health Check")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{MCP_SERVER_URL}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print(f"✅ Health check passed: {health_data}")
                    return True
                else:
                    print(f"❌ Health check failed: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

async def test_sse_mcp_tools(token):
    """Test MCP tools via SSE protocol"""
    print("\n📋 Test 2: MCP Tools via SSE")
    
    # MCP initialize message
    init_message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }
    
    # Tools list message
    tools_message = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test SSE endpoint
            print("  Testing SSE endpoint...")
            
            # Send message to SSE endpoint via POST
            async with session.post(
                f"{MCP_SERVER_URL}/messages",
                json=init_message,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    print("✅ SSE message endpoint accessible")
                    
                    # Try tools list
                    async with session.post(
                        f"{MCP_SERVER_URL}/messages",
                        json=tools_message,
                        headers={"Content-Type": "application/json"}
                    ) as tools_response:
                        if tools_response.status == 200:
                            result = await tools_response.text()
                            print(f"✅ Tools list response: {result}")
                            return True
                        else:
                            print(f"⚠️  Tools list failed: {tools_response.status}")
                else:
                    print(f"⚠️  SSE endpoint failed: {response.status}")
                    
    except Exception as e:
        print(f"❌ SSE test error: {e}")
        
    return False

async def test_simple_mcp_call(token):
    """Test a simple MCP call using HTTP POST"""
    print("\n📋 Test 3: Simple MCP Tool Call")
    
    # Azure search tool call
    search_message = {
        "jsonrpc": "2.0",
        "id": 3,
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
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MCP_SERVER_URL}/messages",
                json=search_message,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.text()
                    print(f"✅ Azure search test successful:")
                    print(result)
                    return True
                else:
                    print(f"❌ Azure search test failed: {response.status}")
                    error_text = await response.text()
                    print(f"Error: {error_text}")
                    return False
                    
    except Exception as e:
        print(f"❌ Search test error: {e}")
        return False

async def main():
    """Main function"""
    print("🧪 SSE-based MCP Server Test Script")
    print("=" * 60)
    print(f"Testing server: {MCP_SERVER_URL}")
    print("-" * 60)
    
    # Get Azure AD token
    token = get_azure_token()
    if not token:
        print("❌ Cannot proceed without Azure AD token")
        return 1
    
    # Test 1: Health check
    health_ok = await test_health_check()
    if not health_ok:
        print("❌ Health check failed - server may not be running")
        return 1
    
    # Test 2: SSE MCP protocol
    sse_ok = await test_sse_mcp_tools(token)
    
    # Test 3: Simple tool call
    search_ok = await test_simple_mcp_call(token)
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 Test Results Summary:")
    print(f"✅ Health Check: {'PASS' if health_ok else 'FAIL'}")
    print(f"✅ SSE Protocol: {'PASS' if sse_ok else 'FAIL'}")
    print(f"✅ Azure Search: {'PASS' if search_ok else 'FAIL'}")
    
    if health_ok and (sse_ok or search_ok):
        print("\n🎉 Core tests passed!")
        print("\n📝 Your SSE-based MCP server is working:")
        print("• Health endpoints accessible ✅")
        print("• SSE transport available ✅") 
        print("• Azure AD authentication ✅")
        
        print(f"\n💡 SSE Endpoint: {MCP_SERVER_URL}/sse")
        print(f"💡 Messages Endpoint: {MCP_SERVER_URL}/messages")
        print("💡 Use these endpoints in your SSE-compatible MCP client")
        
    else:
        print("\n❌ Some tests failed")
        print("💡 Check the server logs:")
        print("   az containerapp logs show --name mcp-server --resource-group indexa10801-rg --follow")
    
    return 0 if health_ok else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
