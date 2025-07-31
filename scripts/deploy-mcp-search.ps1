# Azure Container Apps - MCP Search Service Deployment Script
# This script deploys the MCP Search Service as a second container app

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
    Write-InfoLog "Starting MCP Search Service deployment..."

    # Load configuration
    if (!(Test-Path $ConfigFile)) {
        Write-ErrorLog "Configuration file '$ConfigFile' not found. Run infrastructure deployment first."
        exit 1
    }

    $Config = Get-Content $ConfigFile | ConvertFrom-Json
    
    # MCP Search Service specific configuration
    $McpAppName = "mcp-search-app"
    $McpImageName = "mcp-search-service"
    $McpPort = 50052
    
    Write-InfoLog "Loaded configuration from $ConfigFile"
    Write-InfoLog "Resource Group: $($Config.ResourceGroup)"
    Write-InfoLog "ACR Name: $($Config.AcrName)"
    Write-InfoLog "MCP App Name: $McpAppName"

    # Validate that critical infrastructure exists before proceeding
    Write-InfoLog "Validating infrastructure components before MCP deployment..."
    
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

    # Step 1: Build MCP Search container image in Azure Container Registry
    Write-InfoLog "Building MCP Search container image using Azure Container Registry..."
    try {
        # Set console encoding to UTF-8 to handle special characters
        $originalEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        
        Write-InfoLog "Starting ACR build process for MCP Search Service..."
        # Build from root directory so Dockerfile can access ms/ directory structure  
        az acr build --registry $Config.AcrName --image "$($McpImageName):latest" --file "ms/mcp-search-service/Dockerfile" .
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "ACR build failed with exit code: $LASTEXITCODE"
            exit 1
        }
        Write-SuccessLog "MCP Search container image built successfully in the cloud"
        
        # Get the new image digest
        $imageDigest = az acr repository show --name $Config.AcrName --image "$($McpImageName):latest" --query "digest" -o tsv
        if ($LASTEXITCODE -ne 0) {
            Write-WarningLog "Could not retrieve image digest, but build was successful"
        } else {
            Write-InfoLog "New image digest: $imageDigest"
        }
        
        # Restore original encoding
        [Console]::OutputEncoding = $originalEncoding
    }
    catch {
        Write-ErrorLog "MCP Search container build failed: $_"
        exit 1
    }

    # Step 2: Check if MCP Search Container App already exists
    Write-InfoLog "Checking if MCP Search Container App exists..."
    $existingMcpApp = az containerapp show --name $McpAppName --resource-group $Config.ResourceGroup --output json 2>$null

    if ($existingMcpApp) {
        # Update existing app with specific image digest to force refresh AND update environment variables
        Write-InfoLog "Updating existing MCP Search Container App '$McpAppName' with new image and environment variables..."
        az containerapp update `
            --name $McpAppName `
            --resource-group $Config.ResourceGroup `
            --image "$($Config.AcrName).azurecr.io/$($McpImageName)@$imageDigest" `
            --set-env-vars "AZURE_SEARCH_SERVICE_NAME=$($Config.SearchService)" "AZURE_SEARCH_INDEX_NAME=documents" "SEARCH_API_VERSION=2024-07-01" "MCP_HTTP_PORT=$McpPort" "MCP_SEARCH_TOKEN=$($Config.McpSearchToken)" "AZURE_TENANT_ID=$($Config.AzureTenantId)" "JWT_ISSUER=https://sts.windows.net/$($Config.AzureTenantId)/" "JWT_AUDIENCE=$($Config.McpJwtAudience)" "AZURE_CLIENT_ID=$($Config.ManagedIdentityClientId)"
        
        if ($LASTEXITCODE -ne 0) {
            throw "MCP Search Container App update failed"
        }
        Write-SuccessLog "MCP Search Container App updated successfully with new image and environment variables"
        
        # Restart the app to ensure fresh deployment
        Write-InfoLog "Restarting MCP Search Container App..."
        $latestRevision = az containerapp revision list --name $McpAppName --resource-group $Config.ResourceGroup --query "[0].name" -o tsv
        
        if ($latestRevision) {
            az containerapp revision restart --name $McpAppName --resource-group $Config.ResourceGroup --revision $latestRevision
            if ($LASTEXITCODE -eq 0) {
                Write-SuccessLog "MCP Search Container App restarted successfully"
            } else {
                Write-WarningLog "MCP Search Container App restart failed, but update was successful"
            }
        }
    } else {
        # Create new MCP Search Container App
        Write-InfoLog "Creating new MCP Search Container App '$McpAppName'..."
        
        # Get ACR admin credentials
        $acrCreds = az acr credential show --name $Config.AcrName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json
        
        # Create Container App with MCP Search specific settings
        Write-InfoLog "Creating MCP Search Container App: $McpAppName"
        $createResult = az containerapp create `
            --name $McpAppName `
            --resource-group $Config.ResourceGroup `
            --environment $Config.AcaEnv `
            --image "$($Config.AcrName).azurecr.io/$($McpImageName):latest" `
            --registry-server "$($Config.AcrName).azurecr.io" `
            --registry-username $acrCreds.username `
            --registry-password $acrCreds.passwords[0].value `
            --target-port $McpPort `
            --ingress external `
            --min-replicas 1 `
            --max-replicas 2 `
            --cpu 0.25 `
            --memory 0.5Gi `
            --user-assigned $Config.ManagedIdentityId `
            --env-vars "AZURE_SEARCH_SERVICE_NAME=$($Config.SearchService)" "AZURE_SEARCH_INDEX_NAME=documents" "SEARCH_API_VERSION=2024-07-01" "MCP_HTTP_PORT=$McpPort" "MCP_SEARCH_TOKEN=$($Config.McpSearchToken)" "AZURE_TENANT_ID=$($Config.AzureTenantId)" "JWT_ISSUER=https://sts.windows.net/$($Config.AzureTenantId)/" "JWT_AUDIENCE=$($Config.McpJwtAudience)" "AZURE_CLIENT_ID=$($Config.ManagedIdentityClientId)"

        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "MCP Search Container App creation failed with exit code: $LASTEXITCODE"
            exit 1
        }
        Write-SuccessLog "MCP Search Container App created successfully"
    }

    # Step 3: Get MCP Search Container App details
    Write-InfoLog "Getting MCP Search Container App details..."
    $mcpAppDetails = az containerapp show --name $McpAppName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json
    
    if (!$mcpAppDetails) {
        throw "Failed to get MCP Search Container App details"
    }

    # Step 4: Update deployment config with MCP Search info
    Write-InfoLog "Updating deployment configuration with MCP Search details..."
    $Config | Add-Member -Name "McpAppName" -Value $McpAppName -MemberType NoteProperty -Force
    $Config | Add-Member -Name "McpImageName" -Value $McpImageName -MemberType NoteProperty -Force
    $Config | Add-Member -Name "McpPort" -Value $McpPort -MemberType NoteProperty -Force
    $Config | Add-Member -Name "McpAppUrl" -Value "https://$($mcpAppDetails.properties.configuration.ingress.fqdn)" -MemberType NoteProperty -Force
    
    # Save updated config
    $Config | ConvertTo-Json -Depth 10 | Set-Content $ConfigFile

    # Display deployment summary
    Write-SuccessLog "MCP Search Service deployment completed successfully!"
    Write-Host ""
    Write-Host "=== MCP SEARCH DEPLOYMENT SUMMARY ===" -ForegroundColor Cyan
    Write-Host "Container built in Azure Container Registry"
    Write-Host "MCP Search Container App deployed/updated"
    Write-Host ""
    Write-Host "=== MCP SEARCH ACCESS INFORMATION ===" -ForegroundColor Cyan
    Write-Host "App Name: $McpAppName"
    Write-Host "Status: $($mcpAppDetails.properties.runningStatus)"
    Write-Host "Public URL: https://$($mcpAppDetails.properties.configuration.ingress.fqdn)"
    Write-Host "Health Check: https://$($mcpAppDetails.properties.configuration.ingress.fqdn)/health"
    Write-Host "API Docs: https://$($mcpAppDetails.properties.configuration.ingress.fqdn)/docs"
    Write-Host "Container Image: $($Config.AcrName).azurecr.io/$($McpImageName):latest"
    Write-Host "Valid Token: [Token from configuration]"
    Write-Host ""
    Write-Host "=== TESTING MCP SEARCH ===" -ForegroundColor Yellow
    Write-Host "Test search endpoint:"
    Write-Host 'curl -X POST "https://$($mcpAppDetails.properties.configuration.ingress.fqdn)/search" \'
    Write-Host '  -H "Authorization: Bearer [YOUR_TOKEN_HERE]" \'
    Write-Host '  -H "Content-Type: application/json" \'
    Write-Host '  -d "{\"query\": \"test\", \"top\": 5}"'
    Write-Host ""
    Write-Host "=== MONITORING MCP SEARCH ===" -ForegroundColor Yellow
    Write-Host "View real-time logs:"
    Write-Host "az containerapp logs show --name $McpAppName --resource-group $($Config.ResourceGroup) --follow"
    Write-Host ""

    if ($mcpAppDetails.properties.runningStatus -eq "Running") {
        Write-SuccessLog "Your MCP Search Service is now fully deployed and running!"
    } else {
        Write-WarningLog "MCP Search Container App is not running yet. Status: $($mcpAppDetails.properties.runningStatus)"
        Write-InfoLog "Check the logs for more details"
    }

}
catch {
    Write-ErrorLog "MCP Search Service deployment failed: $_"
    Write-InfoLog "Check the Azure portal or run 'az containerapp logs show --name $McpAppName --resource-group $($Config.ResourceGroup)' for more details"
    exit 1
}
