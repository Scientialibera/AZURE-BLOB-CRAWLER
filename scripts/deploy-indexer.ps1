# Azure Container Apps - Cloud-Native Deployment Script
# This script builds the container in Azure and deploys it to Container Apps

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
    Write-InfoLog "Starting cloud-native container deployment..."

    # Load configuration
    if (!(Test-Path $ConfigFile)) {
        Write-ErrorLog "Configuration file '$ConfigFile' not found. Run infrastructure deployment first."
        exit 1
    }

    $Config = Get-Content $ConfigFile | ConvertFrom-Json
    
    Write-InfoLog "Loaded configuration from $ConfigFile"
    Write-InfoLog "Resource Group: $($Config.ResourceGroup)"
    Write-InfoLog "ACR Name: $($Config.AcrName)"
    Write-InfoLog "App Name: $($Config.AppName)"

    # Validate that critical infrastructure exists before proceeding
    Write-InfoLog "Validating infrastructure components before container deployment..."
    
    # Check if Container Apps Environment exists (critical for deployment)
    $acaEnvExists = az containerapp env show --name $($Config.AcaEnv) --resource-group $($Config.ResourceGroup) --query "name" -o tsv 2>$null
    if ($acaEnvExists -ne $Config.AcaEnv) {
        Write-ErrorLog "Container Apps Environment '$($Config.AcaEnv)' not found!"
        Write-ErrorLog "This indicates the infrastructure deployment failed or Container Apps quota was exceeded."
        Write-ErrorLog "Please run the infrastructure deployment script first and ensure it completes successfully."
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

    # Step 1: Build container image in Azure Container Registry (cloud-native)
    Write-InfoLog "Building indexer container image using Azure Container Registry (cloud build)..."
    # Build from root directory with dockerfile path specified
    try {
        # Set console encoding to UTF-8 to handle special characters
        $originalEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        
        # Build from root directory but specify dockerfile path
        Write-InfoLog "Starting ACR build process for indexer app from root directory..."
        az acr build --registry $Config.AcrName --image "indexer-app:latest" --file "services/indexer_app/Dockerfile" .
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "ACR build failed with exit code: $LASTEXITCODE"
            Write-ErrorLog "This could be due to:"
            Write-ErrorLog "  • Network connectivity issues"
            Write-ErrorLog "  • ACR quota limits"
            Write-ErrorLog "  • Docker build errors in your application"
            Write-ErrorLog "  • Insufficient permissions on ACR"
            exit 1
        }
        Write-SuccessLog "Container image built successfully in the cloud"
        
        # Get the new image digest
        $imageDigest = az acr repository show --name $Config.AcrName --image "indexer-app:latest" --query "digest" -o tsv
        if ($LASTEXITCODE -ne 0) {
            Write-WarningLog "Could not retrieve image digest, but build was successful"
        } else {
            Write-InfoLog "New image digest: $imageDigest"
        }
        
        # Restore original encoding
        [Console]::OutputEncoding = $originalEncoding
    }
    catch {
        Write-ErrorLog "Container build failed: $_"
        exit 1
    }

    # Step 2: Check if Container App already exists
    Write-InfoLog "Checking if Container App exists..."
    $existingApp = az containerapp show --name $Config.AppName --resource-group $Config.ResourceGroup --output json 2>$null

    if ($existingApp) {
        # Update existing app with specific image digest to force refresh
        Write-InfoLog "Updating existing Container App '$($Config.AppName)' with new indexer image digest..."
        az containerapp update `
            --name $Config.AppName `
            --resource-group $Config.ResourceGroup `
            --image "$($Config.AcrName).azurecr.io/indexer-app@$imageDigest" `
            --min-replicas 0 `
            --max-replicas 3 `
            --scale-rule-name "servicebus-queue-rule" `
            --scale-rule-type "azure-servicebus" `
            --scale-rule-metadata "queueName=$($Config.QueueName)" "namespace=$($Config.ServiceBusNamespace)" "messageCount=10" `
            --scale-rule-identity $Config.ManagedIdentityId
        
        if ($LASTEXITCODE -ne 0) {
            throw "Container App update failed"
        }
        Write-SuccessLog "Container App updated successfully with new image and scaling rules"
        
        # Get the new revision name and restart it to ensure fresh deployment
        Write-InfoLog "Restarting Container App to ensure fresh deployment..."
        $latestRevision = az containerapp revision list --name $Config.AppName --resource-group $Config.ResourceGroup --query "[0].name" -o tsv
        
        if ($latestRevision) {
            az containerapp revision restart --name $Config.AppName --resource-group $Config.ResourceGroup --revision $latestRevision
            if ($LASTEXITCODE -eq 0) {
                Write-SuccessLog "Container App restarted successfully"
            } else {
                Write-WarningLog "Container App restart failed, but update was successful"
            }
        }
    } else {
        # Create new Container App with admin credentials (since managed identity had issues)
        Write-InfoLog "Creating new Container App '$($Config.AppName)'..."
        
        # Get ACR admin credentials
        $acrCreds = az acr credential show --name $Config.AcrName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json
        
        # Using managed identity - no need for connection strings or API keys
        Write-InfoLog "Using managed identity authentication - no secrets needed in environment variables"

        # Create Container App with all required settings using user-assigned managed identity
        Write-InfoLog "Creating Container App: $($Config.AppName)"
        $createResult = az containerapp create `
            --name $Config.AppName `
            --resource-group $Config.ResourceGroup `
            --environment $Config.AcaEnv `
            --image "$($Config.AcrName).azurecr.io/indexer-app:latest" `
            --registry-server "$($Config.AcrName).azurecr.io" `
            --registry-username $acrCreds.username `
            --registry-password $acrCreds.passwords[0].value `
            --target-port 50051 `
            --ingress external `
            --min-replicas 0 `
            --max-replicas 3 `
            --cpu 0.5 `
            --memory 1Gi `
            --user-assigned $Config.ManagedIdentityId `
            --scale-rule-name "servicebus-queue-rule" `
            --scale-rule-type "azure-servicebus" `
            --scale-rule-metadata "queueName=$($Config.QueueName)" "namespace=$($Config.ServiceBusNamespace)" "messageCount=10" `
            --scale-rule-identity $Config.ManagedIdentityId `
            --env-vars "AZURE_STORAGE_ACCOUNT_NAME=$($Config.StorageAccount)" "AZURE_SEARCH_SERVICE_NAME=$($Config.SearchService)" "AZURE_OPENAI_SERVICE_NAME=$($Config.OpenAIService)" "SERVICEBUS_NAMESPACE=$($Config.ServiceBusNamespace)" "SERVICEBUS_QUEUE_NAME=$($Config.QueueName)" "AZURE_SEARCH_INDEX_NAME=documents" "CHUNK_MAX_TOKENS=4000" "EMBEDDING_MAX_TOKENS=8000" "MAX_FILE_SIZE_MB=100" "AZURE_CLIENT_ID=$($Config.ManagedIdentityClientId)"

        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Container App creation failed with exit code: $LASTEXITCODE"
            Write-ErrorLog "This could be due to:"
            Write-ErrorLog "  • Container Apps Environment quota exceeded"
            Write-ErrorLog "  • Image pull failures from ACR"
            Write-ErrorLog "  • Insufficient CPU/Memory quota in the region"
            Write-ErrorLog "  • Network connectivity issues"
            Write-ErrorLog "  • Managed identity configuration problems"
            exit 1
        }
        Write-SuccessLog "Container App created successfully"
    }

    # Step 3: Get Container App details
    Write-InfoLog "Getting Container App details..."
    $appDetails = az containerapp show --name $Config.AppName --resource-group $Config.ResourceGroup --output json | ConvertFrom-Json
    
    if (!$appDetails) {
        throw "Failed to get Container App details"
    }

    # Step 4: Create Event Grid subscription for blob storage events (if not exists)
    Write-InfoLog "Setting up Event Grid subscription for blob events..."
    $existingSubscription = az eventgrid event-subscription show --name "BlobCreatedToSB" --source-resource-id $Config.StorageId --output json 2>$null
    
    if (!$existingSubscription) {
        az eventgrid event-subscription create `
            --name "BlobCreatedToSB" `
            --source-resource-id $Config.StorageId `
            --event-types Microsoft.Storage.BlobCreated `
            --endpoint-type servicebusqueue `
            --endpoint $Config.QueueId `
            --output table

        if ($LASTEXITCODE -eq 0) {
            Write-SuccessLog "Event Grid subscription created"
        } else {
            Write-WarningLog "Event Grid subscription creation failed - you may need to create it manually"
        }
    } else {
        Write-InfoLog "Event Grid subscription already exists"
    }

    # Display deployment summary
    Write-SuccessLog "Cloud-native container deployment completed successfully!"
    Write-Host ""
    Write-Host "=== DEPLOYMENT SUMMARY ===" -ForegroundColor Cyan
    Write-Host "Container built in Azure Container Registry"
    Write-Host "Container App deployed/updated"
    Write-Host "Event Grid subscription configured"
    Write-Host ""
    Write-Host "=== ACCESS INFORMATION ===" -ForegroundColor Cyan
    Write-Host "App Name: $($Config.AppName)"
    Write-Host "Status: $($appDetails.properties.runningStatus)"
    Write-Host "Public URL: https://$($appDetails.properties.configuration.ingress.fqdn)"
    Write-Host "Container Image: $($Config.AcrName).azurecr.io/indexer-app:latest"
    Write-Host "Image Digest: $imageDigest"
    Write-Host ""
    Write-Host "=== TESTING ===" -ForegroundColor Yellow
    Write-Host "Upload a test file to trigger the pipeline:"
    Write-Host "az storage blob upload --file <your-file> --container-name $($Config.ContainerName) --name test-file.txt --account-name $($Config.StorageAccount) --auth-mode login"
    Write-Host ""
    Write-Host "=== MONITORING ===" -ForegroundColor Yellow
    Write-Host "View real-time logs:"
    Write-Host "az containerapp logs show --name $($Config.AppName) --resource-group $($Config.ResourceGroup) --follow"
    Write-Host ""
    Write-Host "Check app status:"
    Write-Host ".\scripts\get-deployment-status.ps1"

    if ($appDetails.properties.runningStatus -eq "Running") {
        Write-SuccessLog "Your Azure Event-Driven File Processing Pipeline is now fully deployed and running!"
    } else {
        Write-WarningLog "Container App is not running yet. Status: $($appDetails.properties.runningStatus)"
        Write-InfoLog "Check the logs for more details"
    }

}
catch {
    Write-ErrorLog "Cloud-native container deployment failed: $_"
    Write-InfoLog "Check the Azure portal or run 'az containerapp logs show --name $($Config.AppName) --resource-group $($Config.ResourceGroup)' for more details"
    exit 1
}
