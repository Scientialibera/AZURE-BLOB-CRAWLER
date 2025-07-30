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

    # Get Container App details
    $app = az containerapp show --name $Config.AppName --resource-group $Config.ResourceGroup --output json 2>$null | ConvertFrom-Json
    
    if (!$app) {
        Write-ErrorLog "Container App '$($Config.AppName)' not found"
        exit 1
    }

    # Get revision details
    $revisions = az containerapp revision list --name $Config.AppName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json

    Write-Host ""
    Write-Host "=== CONTAINER APP STATUS ===" -ForegroundColor Cyan
    Write-Host "App Name: $($Config.AppName)"
    Write-Host "Resource Group: $($Config.ResourceGroup)"
    Write-Host "Status: $($app.properties.runningStatus)" -ForegroundColor $(if($app.properties.runningStatus -eq "Running") {"Green"} else {"Yellow"})
    Write-Host "Provisioning State: $($app.properties.provisioningState)"
    Write-Host ""
    
    Write-Host "=== ACCESS INFORMATION ===" -ForegroundColor Cyan
    Write-Host "Public URL: https://$($app.properties.configuration.ingress.fqdn)" -ForegroundColor Green
    Write-Host "Target Port: $($app.properties.configuration.ingress.targetPort)"
    Write-Host "Ingress: $($app.properties.configuration.ingress.external)"
    Write-Host ""
    
    Write-Host "=== CONTAINER INFORMATION ===" -ForegroundColor Cyan
    foreach ($container in $app.properties.template.containers) {
        Write-Host "Container Name: $($container.name)"
        Write-Host "Image: $($container.image)" -ForegroundColor Green
        Write-Host "CPU: $($container.resources.cpu)"
        Write-Host "Memory: $($container.resources.memory)"
    }
    Write-Host ""
    
    Write-Host "=== SCALING INFORMATION ===" -ForegroundColor Cyan
    Write-Host "Min Replicas: $($app.properties.template.scale.minReplicas)"
    Write-Host "Max Replicas: $($app.properties.template.scale.maxReplicas)"
    Write-Host ""
    
    Write-Host "=== REVISIONS ===" -ForegroundColor Cyan
    Write-Host "Total Revisions: $($revisions.Count)"
    Write-Host "Latest Revision: $($app.properties.latestRevisionName)"
    foreach ($revision in $revisions | Sort-Object creationTimeStamp -Descending | Select-Object -First 3) {
        $status = if ($revision.properties.active) { "ACTIVE" } else { "INACTIVE" }
        $color = if ($revision.properties.active) { "Green" } else { "Yellow" }
        Write-Host "  - $($revision.name) ($status) - Created: $($revision.properties.creationTimeStamp)" -ForegroundColor $color
    }
    Write-Host ""
    
    # Check if ACR contains the image
    Write-Host "=== CONTAINER REGISTRY ===" -ForegroundColor Cyan
    $repos = az acr repository list --name $Config.AcrName --output json 2>$null | ConvertFrom-Json
    if ($repos -contains "indexer-app") {
        $tags = az acr repository show-tags --name $Config.AcrName --repository "indexer-app" --output json | ConvertFrom-Json
        Write-Host "ACR Repository: $($Config.AcrName).azurecr.io/indexer-app"
        Write-Host "Available Tags: $($tags -join ', ')"
    } else {
        Write-WarningLog "No 'indexer-app' repository found in ACR"
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
