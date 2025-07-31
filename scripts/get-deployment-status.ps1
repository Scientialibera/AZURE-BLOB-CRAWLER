# Azure Container Apps - Deployment Status Script
# This script shows the current status of your deployed Container App

param(
    [string]$ConfigFile = "scripts\deployment-config.json"
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
    Write-InfoLog "Checking Azure Container Apps deployment status..."

    # Load configuration
    if (!(Test-Path $ConfigFile)) {
        Write-ErrorLog "Configuration file '$ConfigFile' not found."
        exit 1
    }

    $Config = Get-Content $ConfigFile | ConvertFrom-Json

    # Get Main Container App details
    $app = az containerapp show --name $Config.AppName --resource-group $Config.ResourceGroup --output json 2>$null | ConvertFrom-Json
    
    if (!$app) {
        Write-ErrorLog "Container App '$($Config.AppName)' not found"
        exit 1
    }

    # Get MCP Search Container App details (if exists)
    $mcpApp = $null
    $mcpAppName = if ($Config.McpAppName) { $Config.McpAppName } else { "mcp-search-app" }
    $mcpApp = az containerapp show --name $mcpAppName --resource-group $Config.ResourceGroup --output json 2>$null | ConvertFrom-Json

    # Get revision details for main app
    $revisions = az containerapp revision list --name $Config.AppName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json

    Write-Host ""
    Write-Host "=== MAIN CONTAINER APP STATUS ===" -ForegroundColor Cyan
    Write-Host "App Name: $($Config.AppName)"
    Write-Host "Resource Group: $($Config.ResourceGroup)"
    Write-Host "Status: $($app.properties.runningStatus)" -ForegroundColor $(if($app.properties.runningStatus -eq "Running") {"Green"} else {"Yellow"})
    Write-Host "Provisioning State: $($app.properties.provisioningState)"
    Write-Host "Public URL: https://$($app.properties.configuration.ingress.fqdn)" -ForegroundColor Green
    Write-Host ""

    # MCP Search App Status
    if ($mcpApp) {
        Write-Host "=== MCP SEARCH SERVICE STATUS ===" -ForegroundColor Cyan
        Write-Host "App Name: $mcpAppName"
        Write-Host "Status: $($mcpApp.properties.runningStatus)" -ForegroundColor $(if($mcpApp.properties.runningStatus -eq "Running") {"Green"} else {"Yellow"})
        Write-Host "Provisioning State: $($mcpApp.properties.provisioningState)"
        Write-Host "Public URL: https://$($mcpApp.properties.configuration.ingress.fqdn)" -ForegroundColor Green
        Write-Host "Health Check: https://$($mcpApp.properties.configuration.ingress.fqdn)/health" -ForegroundColor Green
        Write-Host "API Docs: https://$($mcpApp.properties.configuration.ingress.fqdn)/docs" -ForegroundColor Green
        Write-Host "Valid Token: [Token from configuration]" -ForegroundColor Yellow
        Write-Host ""
    } else {
        Write-Host "=== MCP SEARCH SERVICE STATUS ===" -ForegroundColor Cyan
        Write-WarningLog "MCP Search Service not deployed yet"
        Write-Host "To deploy: .\scripts\deploy-mcp-search.ps1"
        Write-Host ""
    }
    
    Write-Host "=== CONTAINER INFORMATION ===" -ForegroundColor Cyan
    Write-Host "Main App Containers:"
    foreach ($container in $app.properties.template.containers) {
        Write-Host "  Container Name: $($container.name)"
        Write-Host "  Image: $($container.image)" -ForegroundColor Green
        Write-Host "  CPU: $($container.resources.cpu)"
        Write-Host "  Memory: $($container.resources.memory)"
    }
    
    if ($mcpApp) {
        Write-Host "MCP Search Containers:"
        foreach ($container in $mcpApp.properties.template.containers) {
            Write-Host "  Container Name: $($container.name)"
            Write-Host "  Image: $($container.image)" -ForegroundColor Green
            Write-Host "  CPU: $($container.resources.cpu)"
            Write-Host "  Memory: $($container.resources.memory)"
        }
    }
    Write-Host ""
    
    Write-Host "=== SCALING INFORMATION ===" -ForegroundColor Cyan
    Write-Host "Main App - Min: $($app.properties.template.scale.minReplicas), Max: $($app.properties.template.scale.maxReplicas)"
    if ($mcpApp) {
        Write-Host "MCP Search - Min: $($mcpApp.properties.template.scale.minReplicas), Max: $($mcpApp.properties.template.scale.maxReplicas)"
    }
    Write-Host ""
    
    Write-Host "=== REVISIONS ===" -ForegroundColor Cyan
    Write-Host "Main App - Total Revisions: $($revisions.Count), Latest: $($app.properties.latestRevisionName)"
    foreach ($revision in $revisions | Sort-Object creationTimeStamp -Descending | Select-Object -First 2) {
        $status = if ($revision.properties.active) { "ACTIVE" } else { "INACTIVE" }
        $color = if ($revision.properties.active) { "Green" } else { "Yellow" }
        Write-Host "  - $($revision.name) ($status)" -ForegroundColor $color
    }
    Write-Host ""
    
    # Check if ACR contains the images
    Write-Host "=== CONTAINER REGISTRY ===" -ForegroundColor Cyan
    $repos = az acr repository list --name $Config.AcrName --output json 2>$null | ConvertFrom-Json
    if ($repos -contains "indexer-app") {
        Write-Host "✅ Main App Image: $($Config.AcrName).azurecr.io/indexer-app"
    } else {
        Write-WarningLog "❌ No 'indexer-app' repository found in ACR"
    }
    
    if ($repos -contains "mcp-search-service") {
        Write-Host "✅ MCP Search Image: $($Config.AcrName).azurecr.io/mcp-search-service"
    } else {
        Write-WarningLog "❌ No 'mcp-search-service' repository found in ACR"
    }
    Write-Host ""
    
    Write-Host "=== MANAGEMENT COMMANDS ===" -ForegroundColor Cyan
    Write-Host "View logs:" -ForegroundColor Yellow
    Write-Host "  az containerapp logs show --name $($Config.AppName) --resource-group $($Config.ResourceGroup) --follow"
    Write-Host ""
    Write-Host "Restart app:" -ForegroundColor Yellow
    Write-Host "  az containerapp revision restart --name $($Config.AppName) --resource-group $($Config.ResourceGroup)"
    Write-Host ""
    Write-Host "Update image:" -ForegroundColor Yellow
    Write-Host "  az containerapp update --name $($Config.AppName) --resource-group $($Config.ResourceGroup) --image $($Config.AcrName).azurecr.io/indexer-app:latest"
    Write-Host ""

    if ($app.properties.runningStatus -eq "Running") {
        Write-SuccessLog "Container App is running successfully!"
        Write-InfoLog "You can access your application at: https://$($app.properties.configuration.ingress.fqdn)"
    } else {
        Write-WarningLog "Container App is not running. Status: $($app.properties.runningStatus)"
        Write-InfoLog "Check the logs for more details"
    }

}
catch {
    Write-ErrorLog "Failed to get deployment status: $_"
    exit 1
}
