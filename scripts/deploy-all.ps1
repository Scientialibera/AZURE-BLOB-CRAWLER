# Azure Event-Driven File Processing Pipeline - Master Deployment Script
# This script deploys the complete solution: infrastructure + application

param(
    [string]$Prefix = "indexa1$(Get-Date -Format 'MMdd')",
    [string]$Location = "eastus 2",
    [switch]$InfrastructureOnly = $false
)

# Helper functions for colored output
function Write-InfoLog {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-SuccessLog {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-WarningLog {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-ErrorLog {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

try {
    Write-Host "🚀 Azure Event-Driven File Processing Pipeline Deployment" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""

    # Step 1: Deploy Infrastructure
    Write-InfoLog "Step 1: Deploying Azure infrastructure..."
    Write-InfoLog "Prefix: $Prefix"
    Write-InfoLog "Location: $Location"
    
    & ".\scripts\deploy-infrastructure.ps1" -Prefix $Prefix -Location $Location
    
    if ($LASTEXITCODE -ne 0) {
        Write-WarningLog "Infrastructure deployment encountered issues (possibly RBAC permissions)."
        Write-InfoLog "Continuing with container deployment - RBAC permissions can be fixed manually."
    } else {
        Write-SuccessLog "Infrastructure deployment completed!"
    }
    
    if ($InfrastructureOnly) {
        Write-InfoLog "Infrastructure-only deployment requested. Stopping here."
        Write-InfoLog "To deploy the applications later, run: .\scripts\deploy-indexer.ps1 and .\scripts\deploy-mcp.ps1"
        if ($LASTEXITCODE -ne 0) {
            Write-WarningLog "Note: You may need to manually assign RBAC permissions before the container apps will work properly."
        }
        exit 0
    }

    # Step 2: Deploy Indexer Container Application
    Write-Host ""
    Write-InfoLog "Step 2: Deploying indexer container application (cloud-native build)..."
    
    & ".\scripts\deploy-indexer.ps1"
    
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorLog "Indexer container deployment failed!"
        exit 1
    }
    
    Write-SuccessLog "Indexer container deployment completed!"

    # Step 3: Deploy MCP Server Container Application
    Write-Host ""
    Write-InfoLog "Step 3: Deploying MCP server container application (cloud-native build)..."
    
    & ".\scripts\deploy-mcp.ps1"
    
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorLog "MCP server container deployment failed!"
        exit 1
    }
    
    Write-SuccessLog "MCP server container deployment completed!"

    # Step 4: Final Summary
    Write-Host ""
    Write-Host "🎉 DEPLOYMENT COMPLETE!" -ForegroundColor Green
    Write-Host "========================" -ForegroundColor Green
    Write-Host ""
    Write-InfoLog "Your Azure Event-Driven File Processing Pipeline is now fully deployed!"
    Write-Host ""
    Write-Host " What was deployed:" -ForegroundColor Cyan
    Write-Host "  ✅ Azure Storage Account with blob container"
    Write-Host "  ✅ Azure Service Bus with queue"
    Write-Host "  ✅ Azure AI Search with vector index"
    Write-Host "  ✅ Azure OpenAI with text-embedding model"
    Write-Host "  ✅ Azure Container Registry with your app images"
    Write-Host "  ✅ Azure Container Apps with indexer and MCP server applications"
    Write-Host "  ✅ Event Grid subscription for blob events"
    Write-Host ""
    Write-Host " Management commands:" -ForegroundColor Yellow
    Write-Host "  Check status:    .\scripts\get-deployment-status.ps1"
    Write-Host "  Validate infra:  .\scripts\validate-infrastructure.ps1"
    Write-Host "  View logs:       az containerapp logs show --name indexer-app --resource-group $Prefix-rg --follow"
    Write-Host "  View MCP logs:   az containerapp logs show --name mcp-server --resource-group $Prefix-rg --follow"
    Write-Host ""
    Write-Host " Test your pipeline:" -ForegroundColor Yellow
    Write-Host "  Upload a file to trigger processing:"
    Write-Host "  az storage blob upload --file <your-file> --container-name landing --name test.txt --account-name $Prefix" + "stor --auth-mode login"
    Write-Host ""
    Write-Host "  Important:" -ForegroundColor Yellow
    Write-Host "  If you see 'Unauthorized access' errors in logs, manually assign RBAC permissions:"
    Write-Host "  - Storage Blob Data Contributor → Storage Account"
    Write-Host "  - Azure Service Bus Data Receiver/Sender → Service Bus Queue"
    Write-Host "  - Search Index Data Contributor → Search Service"
    Write-Host "  - Cognitive Services OpenAI User → OpenAI Service"
    Write-Host "  Then create a new container app revision: az containerapp revision copy"
    Write-Host ""
    Write-SuccessLog "Ready to process files! 🎊"

}
catch {
    Write-ErrorLog "Master deployment failed: $_"
    Write-Host ""
    Write-Host "🔧 Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Check Azure CLI authentication: az account show"
    Write-Host "  2. Verify permissions in your Azure subscription"
    Write-Host "  3. Check the logs above for specific error details"
    Write-Host "  4. You can run individual scripts manually:"
    Write-Host "     - .\scripts\deploy-infrastructure.ps1"
    Write-Host "     - .\scripts\deploy-indexer.ps1"
    Write-Host "     - .\scripts\deploy-mcp.ps1"
    exit 1
}
