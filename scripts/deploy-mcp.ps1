# Azure Container Apps - MCP Server Deployment Script
# This script builds the MCP server container in Azure and deploys it to Container Apps

param(
    [string]$ConfigFile = "deployment-config.json"
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

$ErrorActionPreference = "Stop"

try {
    Write-InfoLog "Starting MCP server container deployment..."

    # Load configuration
    if (!(Test-Path $ConfigFile)) {
        Write-ErrorLog "Configuration file '$ConfigFile' not found. Run infrastructure deployment first."
        exit 1
    }

    $Config = Get-Content $ConfigFile | ConvertFrom-Json
    
    Write-InfoLog "Loaded configuration from $ConfigFile"
    Write-InfoLog "Resource Group: $($Config.ResourceGroup)"
    Write-InfoLog "ACR Name: $($Config.AcrName)"
    Write-InfoLog "MCP App Name: mcp-server"

    # Validate that critical infrastructure exists before proceeding
    Write-InfoLog "Validating infrastructure components before MCP server deployment..."
    
    # Check if Container Apps Environment exists (critical for deployment)
    $acaEnvExists = az containerapp env show --name $($Config.AcaEnv) --resource-group $($Config.ResourceGroup) --query "name" -o tsv 2>$null
    if ($acaEnvExists -ne $Config.AcaEnv) {
        Write-ErrorLog "Container Apps Environment '$($Config.AcaEnv)' not found!"
        Write-ErrorLog "Please run the infrastructure deployment script first."
        exit 1
    }
    
    # Check if Container Registry exists
    $acrExists = az acr show --name $($Config.AcrName) --resource-group $($Config.ResourceGroup) --query "name" -o tsv 2>$null
    if ($acrExists -ne $Config.AcrName) {
        Write-ErrorLog "Container Registry '$($Config.AcrName)' not found!"
        Write-ErrorLog "Please run the infrastructure deployment script first."
        exit 1
    }
    
    # Check if Managed Identity exists
    $identityExists = az identity show --name $($Config.ManagedIdentityName) --resource-group $($Config.ResourceGroup) --query "name" -o tsv 2>$null
    if ($identityExists -ne $Config.ManagedIdentityName) {
        Write-ErrorLog "Managed Identity '$($Config.ManagedIdentityName)' not found!"
        Write-ErrorLog "Please run the infrastructure deployment script first."
        exit 1
    }
    
    Write-SuccessLog "Infrastructure validation passed - all critical components found"

    # Step 1: Build MCP server container image in Azure Container Registry
    Write-InfoLog "Building MCP server container image using Azure Container Registry (cloud build)..."
    # Build from root directory with dockerfile path specified
    try {
        # Set console encoding to UTF-8 to handle special characters
        $originalEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        
        # Build from root directory but specify dockerfile path
        Write-InfoLog "Starting ACR build process for MCP server from root directory..."
        az acr build --registry $Config.AcrName --image "mcp-server:latest" --file "services/mcp_server/Dockerfile" .
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "ACR build failed with exit code: $LASTEXITCODE"
            Write-ErrorLog "This could be due to:"
            Write-ErrorLog "  • Network connectivity issues"
            Write-ErrorLog "  • ACR quota limits"
            Write-ErrorLog "  • Docker build errors in your application"
            Write-ErrorLog "  • Insufficient permissions on ACR"
            exit 1
        }
        Write-SuccessLog "MCP server container image built successfully in the cloud"
        
        # Get the new image digest
        $imageDigest = az acr repository show --name $Config.AcrName --image "mcp-server:latest" --query "digest" -o tsv
        if ($LASTEXITCODE -ne 0) {
            Write-WarningLog "Could not retrieve image digest, but build was successful"
        } else {
            Write-InfoLog "New MCP server image digest: $imageDigest"
        }
        
        # Restore original encoding
        [Console]::OutputEncoding = $originalEncoding
    }
    catch {
        Write-ErrorLog "MCP server container build failed: $_"
        exit 1
    }

    # Step 2: Check if MCP Server Container App already exists
    Write-InfoLog "Checking if MCP Server Container App exists..."
    $existingApp = az containerapp show --name "mcp-server" --resource-group $Config.ResourceGroup --output json 2>$null

    if ($existingApp) {
        # Update existing app with specific image digest to force refresh
        Write-InfoLog "Updating existing MCP Server Container App with new image digest..."
        az containerapp update `
            --name "mcp-server" `
            --resource-group $Config.ResourceGroup `
            --image "$($Config.AcrName).azurecr.io/mcp-server@$imageDigest" `
            --set-env-vars "AZURE_SEARCH_SERVICE_NAME=$($Config.SearchService)" "AZURE_OPENAI_SERVICE_NAME=$($Config.OpenAIService)" "AZURE_SEARCH_INDEX_NAME=documents" "AZURE_CLIENT_ID=$($Config.ManagedIdentityClientId)" "AZURE_TENANT_ID=$($Config.TenantId)"
        
        if ($LASTEXITCODE -ne 0) {
            throw "MCP Server Container App update failed"
        }
        Write-SuccessLog "MCP Server Container App updated successfully with new image and environment variables"
        
        # Get the new revision name and restart it to ensure fresh deployment
        Write-InfoLog "Restarting MCP Server Container App to ensure fresh deployment..."
        $latestRevision = az containerapp revision list --name "mcp-server" --resource-group $Config.ResourceGroup --query "[0].name" -o tsv
        
        if ($latestRevision) {
            az containerapp revision restart --name "mcp-server" --resource-group $Config.ResourceGroup --revision $latestRevision
            if ($LASTEXITCODE -eq 0) {
                Write-SuccessLog "MCP Server Container App restarted successfully"
            } else {
                Write-WarningLog "MCP Server Container App restart failed, but update was successful"
            }
        }
    } else {
        # Create new MCP Server Container App
        Write-InfoLog "Creating new MCP Server Container App..."
        
        # Get ACR admin credentials
        $acrCreds = az acr credential show --name $Config.AcrName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json
        
        # Using managed identity authentication - no need for connection strings or API keys
        Write-InfoLog "Using managed identity authentication for MCP server - no secrets needed in environment variables"

        # Create Container App with all required settings using user-assigned managed identity
        Write-InfoLog "Creating MCP Server Container App"
        $createResult = az containerapp create `
            --name "mcp-server" `
            --resource-group $Config.ResourceGroup `
            --environment $Config.AcaEnv `
            --image "$($Config.AcrName).azurecr.io/mcp-server:latest" `
            --registry-server "$($Config.AcrName).azurecr.io" `
            --registry-username $acrCreds.username `
            --registry-password $acrCreds.passwords[0].value `
            --target-port 8080 `
            --ingress external `
            --min-replicas 1 `
            --max-replicas 2 `
            --cpu 0.25 `
            --memory 0.5Gi `
            --user-assigned $Config.ManagedIdentityId `
            --env-vars "AZURE_SEARCH_SERVICE_NAME=$($Config.SearchService)" "AZURE_OPENAI_SERVICE_NAME=$($Config.OpenAIService)" "AZURE_SEARCH_INDEX_NAME=documents" "AZURE_CLIENT_ID=$($Config.ManagedIdentityClientId)" "AZURE_TENANT_ID=$($Config.TenantId)"

        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "MCP Server Container App creation failed with exit code: $LASTEXITCODE"
            Write-ErrorLog "This could be due to:"
            Write-ErrorLog "  • Container Apps Environment quota exceeded"
            Write-ErrorLog "  • Image pull failures from ACR"
            Write-ErrorLog "  • Insufficient CPU/Memory quota in the region"
            Write-ErrorLog "  • Network connectivity issues"
            Write-ErrorLog "  • Managed identity configuration problems"
            exit 1
        }
        Write-SuccessLog "MCP Server Container App created successfully"
    }

    # Step 3: Get MCP Server Container App details
    Write-InfoLog "Getting MCP Server Container App details..."
    $appDetails = az containerapp show --name "mcp-server" --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json
    
    if (!$appDetails) {
        throw "Failed to get MCP Server Container App details"
    }

    # Display deployment summary
    Write-SuccessLog "MCP Server deployment completed successfully!"
    Write-Host ""
    Write-Host "=== MCP SERVER DEPLOYMENT SUMMARY ===" -ForegroundColor Cyan
    Write-Host "Container built in Azure Container Registry"
    Write-Host "MCP Server Container App deployed/updated"
    Write-Host ""
    Write-Host "=== MCP SERVER ACCESS INFORMATION ===" -ForegroundColor Cyan
    Write-Host "App Name: mcp-server"
    Write-Host "Status: $($appDetails.properties.runningStatus)"
    Write-Host "Public URL: https://$($appDetails.properties.configuration.ingress.fqdn)"
    Write-Host "Container Image: $($Config.AcrName).azurecr.io/mcp-server:latest"
    Write-Host "Image Digest: $imageDigest"
    Write-Host ""
    Write-Host "=== MONITORING ===" -ForegroundColor Yellow
    Write-Host "View real-time logs:"
    Write-Host "az containerapp logs show --name mcp-server --resource-group $($Config.ResourceGroup) --follow"
    Write-Host ""
    Write-Host "Check app status:"
    Write-Host ".\scripts\get-deployment-status.ps1"

    if ($appDetails.properties.runningStatus -eq "Running") {
        Write-SuccessLog "Your MCP Server is now fully deployed and running!"
    } else {
        Write-WarningLog "MCP Server Container App is not running yet. Status: $($appDetails.properties.runningStatus)"
        Write-InfoLog "Check the logs for more details"
    }

}
catch {
    Write-ErrorLog "MCP Server deployment failed: $_"
    Write-InfoLog "Check the Azure portal or run 'az containerapp logs show --name mcp-server --resource-group $($Config.ResourceGroup)' for more details"
    exit 1
}
