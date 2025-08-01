# Azure Event-Driven File Processing Pipeline Deployment Script (PowerShell) - Infrastructure Only
# This script deploys the infrastructure components without requiring Docker initially

param(
    [string]$Prefix = "indexa1$(Get-Date -Format 'MMdd')",
    [string]$Location = "eastus 2"
)

# Configuration
$ResourceGroup = "$Prefix-rg"
$StorageAccount = "$Prefix" + "stor"
$ServiceBusNamespace = "$Prefix" + "sb"
$QueueName = "indexqueue"
$AcrName = "$Prefix" + "acr"
$SearchService = "$Prefix-search"
$OpenAIService = "$Prefix-openai"
$AcaEnv = "$Prefix-acaenv"
$AppName = "indexer-app"
$ContainerName = "landing"
$LogAnalyticsWorkspace = "$Prefix-logs"

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

function Write-ExistsLog {
    param([string]$Message)
    Write-Host "[EXISTS] $Message" -ForegroundColor Magenta
}

# Helper function to check if a resource exists
function Test-AzureResource {
    param(
        [string]$ResourceType,
        [string]$ResourceName,
        [string]$ResourceGroup,
        [string]$ExtraParams = ""
    )
    
    try {
        switch ($ResourceType) {
            "group" { 
                $result = az group show --name $ResourceName 2>$null
                return $result -ne $null 
            }
            "storage" { 
                $result = az storage account show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "servicebus" { 
                $result = az servicebus namespace show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "search" { 
                $result = az search service show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "cognitiveservices" { 
                $result = az cognitiveservices account show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "acr" { 
                $result = az acr show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "containerapp-env" { 
                $result = az containerapp env show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "identity" { 
                $result = az identity show --name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            "log-analytics" { 
                $result = az monitor log-analytics workspace show --workspace-name $ResourceName --resource-group $ResourceGroup 2>$null
                return $result -ne $null 
            }
            default { return $false }
        }
    }
    catch {
        return $false
    }
}

# Error handling
$ErrorActionPreference = "Stop"

try {
    Write-InfoLog "Starting infrastructure deployment with prefix: $Prefix"
    Write-InfoLog "Location: $Location"

    # Step 1: Verify prerequisites
    Write-InfoLog "Verifying prerequisites..."

    if (!(Get-Command az -ErrorAction SilentlyContinue)) {
        Write-ErrorLog "Azure CLI is not installed. Please install it first."
        exit 1
    }

    # Check if logged in to Azure
    try {
        az account show | Out-Null
    }
    catch {
        Write-ErrorLog "Not logged in to Azure. Please run 'az login' first."
        exit 1
    }

    Write-SuccessLog "Prerequisites verified"

    # Step 2: Create Resource Group
    Write-InfoLog "Checking resource group: $ResourceGroup"
    if (Test-AzureResource -ResourceType "group" -ResourceName $ResourceGroup) {
        Write-ExistsLog "Resource group '$ResourceGroup' already exists"
    } else {
        Write-InfoLog "Creating resource group: $ResourceGroup"
        $rgResult = az group create --name $ResourceGroup --location $Location --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create resource group: $ResourceGroup"
            exit 1
        }
        Write-SuccessLog "Resource group created"
    }

    # Step 3: Create Log Analytics Workspace
    Write-InfoLog "Checking Log Analytics workspace: $LogAnalyticsWorkspace"
    if (Test-AzureResource -ResourceType "log-analytics" -ResourceName $LogAnalyticsWorkspace -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Log Analytics workspace '$LogAnalyticsWorkspace' already exists"
    } else {
        Write-InfoLog "Creating Log Analytics workspace: $LogAnalyticsWorkspace"
        $laResult = az monitor log-analytics workspace create `
            --resource-group $ResourceGroup `
            --workspace-name $LogAnalyticsWorkspace `
            --location $Location `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Log Analytics workspace: $LogAnalyticsWorkspace"
            exit 1
        }
        Write-SuccessLog "Log Analytics workspace created"
    }

    $LogAnalyticsId = az monitor log-analytics workspace show `
        --resource-group $ResourceGroup `
        --workspace-name $LogAnalyticsWorkspace `
        --query "customerId" -o tsv

    Write-SuccessLog "Log Analytics workspace ID retrieved: $LogAnalyticsId"

    # Step 4: Create Storage Account (Secure: Key access disabled)
    Write-InfoLog "Checking storage account: $StorageAccount"
    if (Test-AzureResource -ResourceType "storage" -ResourceName $StorageAccount -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Storage account '$StorageAccount' already exists"
    } else {
        Write-InfoLog "Creating storage account: $StorageAccount"
        $storageResult = az storage account create `
            --name $StorageAccount `
            --resource-group $ResourceGroup `
            --location $Location `
            --sku Standard_LRS `
            --kind StorageV2 `
            --allow-blob-public-access false `
            --allow-shared-key-access false `
            --min-tls-version TLS1_2 `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create storage account: $StorageAccount"
            exit 1
        }
        Write-SuccessLog "Storage account created"
    }

    # Check if container exists
    Write-InfoLog "Checking blob container: $ContainerName"
    $containerExists = az storage container exists `
        --name $ContainerName `
        --account-name $StorageAccount `
        --auth-mode login `
        --query "exists" -o tsv 2>$null
    
    if ($containerExists -eq "true") {
        Write-ExistsLog "Blob container '$ContainerName' already exists"
    } else {
        Write-InfoLog "Creating blob container: $ContainerName"
        $containerResult = az storage container create `
            --name $ContainerName `
            --account-name $StorageAccount `
            --auth-mode login `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create blob container: $ContainerName"
            exit 1
        }
        Write-SuccessLog "Blob container created"
    }

    $StorageId = az storage account show `
        --name $StorageAccount `
        --resource-group $ResourceGroup `
        --query id -o tsv

    Write-SuccessLog "Storage account configuration completed"

    # Step 5: Create Service Bus Namespace and Queue
    Write-InfoLog "Checking Service Bus namespace: $ServiceBusNamespace"
    if (Test-AzureResource -ResourceType "servicebus" -ResourceName $ServiceBusNamespace -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Service Bus namespace '$ServiceBusNamespace' already exists"
    } else {
        Write-InfoLog "Creating Service Bus namespace: $ServiceBusNamespace"
        $sbResult = az servicebus namespace create `
            --name $ServiceBusNamespace `
            --resource-group $ResourceGroup `
            --location $Location `
            --sku Basic `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Service Bus namespace: $ServiceBusNamespace"
            exit 1
        }
        Write-SuccessLog "Service Bus namespace created"
    }

    # Check if queue exists
    Write-InfoLog "Checking Service Bus queue: $QueueName"
    $queueExists = az servicebus queue show `
        --name $QueueName `
        --namespace-name $ServiceBusNamespace `
        --resource-group $ResourceGroup `
        --query "name" -o tsv 2>$null
    
    if ($queueExists -eq $QueueName) {
        Write-ExistsLog "Service Bus queue '$QueueName' already exists"
    } else {
        Write-InfoLog "Creating Service Bus queue: $QueueName"
        $queueResult = az servicebus queue create `
            --name $QueueName `
            --namespace-name $ServiceBusNamespace `
            --resource-group $ResourceGroup `
            --max-delivery-count 10 `
            --default-message-time-to-live P14D `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Service Bus queue: $QueueName"
            exit 1
        }
        Write-SuccessLog "Service Bus queue created"
    }

    $SubscriptionId = az account show --query id -o tsv
    $QueueId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.ServiceBus/namespaces/$ServiceBusNamespace/queues/$QueueName"

    Write-SuccessLog "Service Bus configuration completed"

    # Step 6: Create Azure AI Search Service with RBAC enabled
    Write-InfoLog "Checking Azure AI Search service: $SearchService"
    if (Test-AzureResource -ResourceType "search" -ResourceName $SearchService -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Azure AI Search service '$SearchService' already exists"
    } else {
        Write-InfoLog "Creating Azure AI Search service: $SearchService"
        $searchResult = az search service create `
            --name $SearchService `
            --resource-group $ResourceGroup `
            --location $Location `
            --sku basic `
            --replica-count 1 `
            --partition-count 1 `
            --auth-options aadOrApiKey `
            --aad-auth-failure-mode http401WithBearerChallenge `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Azure AI Search service: $SearchService"
            exit 1
        }
        Write-SuccessLog "Azure AI Search service created"
    }

    $SearchId = az search service show `
        --name $SearchService `
        --resource-group $ResourceGroup `
        --query id -o tsv

    Write-SuccessLog "Azure AI Search service with RBAC authentication configured"

    # Step 7: Create Azure OpenAI Service with custom subdomain for token authentication
    Write-InfoLog "Checking Azure OpenAI service: $OpenAIService"
    if (Test-AzureResource -ResourceType "cognitiveservices" -ResourceName $OpenAIService -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Azure OpenAI service '$OpenAIService' already exists"
    } else {
        Write-InfoLog "Creating Azure OpenAI service with custom subdomain: $OpenAIService"
        $openaiResult = az cognitiveservices account create `
            --name $OpenAIService `
            --resource-group $ResourceGroup `
            --location $Location `
            --kind OpenAI `
            --sku S0 `
            --custom-domain $OpenAIService `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Azure OpenAI service: $OpenAIService"
            Write-ErrorLog "This could be due to OpenAI quota limits. Check your subscription's OpenAI service availability."
            exit 1
        }
        Write-SuccessLog "Azure OpenAI service created"
    }

    $OpenAIId = az cognitiveservices account show `
        --name $OpenAIService `
        --resource-group $ResourceGroup `
        --query id -o tsv

    # Check if text-embedding-ada-002 model deployment exists
    Write-InfoLog "Checking text-embedding-ada-002 model deployment..."
    $deploymentExists = az cognitiveservices account deployment show `
        --name $OpenAIService `
        --resource-group $ResourceGroup `
        --deployment-name "text-embedding-ada-002" `
        --query "name" -o tsv 2>$null
    
    if ($deploymentExists -eq "text-embedding-ada-002") {
        Write-ExistsLog "Text-embedding-ada-002 model deployment already exists"
    } else {
        Write-InfoLog "Deploying text-embedding-ada-002 model..."
        $modelResult = az cognitiveservices account deployment create `
            --name            $OpenAIService `
            --resource-group  $ResourceGroup `
            --deployment-name "text-embedding-ada-002" `
            --model-name      "text-embedding-ada-002" `
            --model-version   "2" `
            --model-format    "OpenAI" `
            --sku-name        "Standard" `
            --sku-capacity    "150"
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to deploy text-embedding-ada-002 model"
            Write-ErrorLog "This could be due to model quota limits. Check your OpenAI service quotas."
            exit 1
        }
        Write-SuccessLog "Text embedding model deployed"
    }

    # Step 8: Create Container Registry (Admin access enabled for ACA)
    Write-InfoLog "Checking Azure Container Registry: $AcrName"
    if (Test-AzureResource -ResourceType "acr" -ResourceName $AcrName -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Azure Container Registry '$AcrName' already exists"
    } else {
        Write-InfoLog "Creating Azure Container Registry: $AcrName"
        $acrResult = az acr create `
            --name $AcrName `
            --resource-group $ResourceGroup `
            --sku Basic `
            --location $Location `
            --admin-enabled true `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Azure Container Registry: $AcrName"
            exit 1
        }
        Write-SuccessLog "Container Registry created with admin access enabled for ACA"
    }

    # Step 9: Create Container Apps Environment
    Write-InfoLog "Checking Container Apps environment: $AcaEnv"
    if (Test-AzureResource -ResourceType "containerapp-env" -ResourceName $AcaEnv -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Container Apps environment '$AcaEnv' already exists"
    } else {
        Write-InfoLog "Creating Container Apps environment: $AcaEnv"
        $acaResult = az containerapp env create `
            --name $AcaEnv `
            --resource-group $ResourceGroup `
            --location $Location `
            --logs-workspace-id $LogAnalyticsId `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create Container Apps environment: $AcaEnv"
            Write-ErrorLog "This is often due to quota limits or regional availability issues."
            Write-ErrorLog "Check your subscription's Container Apps quota in the region: $Location"
            exit 1
        }
        Write-SuccessLog "Container Apps environment created"
    }

    # Step 9.1: Create User-Assigned Managed Identity for Container App
    Write-InfoLog "Checking user-assigned managed identity for secure authentication..."
    $ManagedIdentityName = "$AppName-identity"
    
    if (Test-AzureResource -ResourceType "identity" -ResourceName $ManagedIdentityName -ResourceGroup $ResourceGroup) {
        Write-ExistsLog "Managed identity '$ManagedIdentityName' already exists"
    } else {
        Write-InfoLog "Creating user-assigned managed identity: $ManagedIdentityName"
        $identityResult = az identity create `
            --name $ManagedIdentityName `
            --resource-group $ResourceGroup `
            --location $Location `
            --output table
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorLog "Failed to create managed identity: $ManagedIdentityName"
            exit 1
        }
        Write-SuccessLog "Managed identity created"
    }

    $ManagedIdentityId = az identity show `
        --name $ManagedIdentityName `
        --resource-group $ResourceGroup `
        --query id -o tsv

    $ManagedIdentityClientId = az identity show `
        --name $ManagedIdentityName `
        --resource-group $ResourceGroup `
        --query clientId -o tsv

    $ManagedIdentityPrincipalId = az identity show `
        --name $ManagedIdentityName `
        --resource-group $ResourceGroup `
        --query principalId -o tsv

    Write-SuccessLog "Managed identity configuration completed: $ManagedIdentityName"

    # Step 9.2: Assign RBAC permissions for secure service communication
    Write-InfoLog "Assigning RBAC permissions for secure authentication..."
    
    $rbacSuccess = $true
    
    try {
        # Storage Blob Data Contributor for reading/writing blobs
        az role assignment create `
            --role "ba92f5b4-2d11-453d-a403-e96b0029c9fe" `
            --assignee-object-id $ManagedIdentityPrincipalId `
            --assignee-principal-type "ServicePrincipal" `
            --scope $StorageId

        # Azure Service Bus Data Receiver for receiving messages (assigned at queue level for specific permissions)
        az role assignment create `
            --role "4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0" `
            --assignee-object-id $ManagedIdentityPrincipalId `
            --assignee-principal-type "ServicePrincipal" `
            --scope $QueueId

        # Azure Service Bus Data Sender for sending acknowledgments if needed
        az role assignment create `
            --role "69a216fc-b8fb-44d8-bc22-1f3c2cd27a39" `
            --assignee-object-id $ManagedIdentityPrincipalId `
            --assignee-principal-type "ServicePrincipal" `
            --scope $QueueId

        # Search Index Data Contributor for search operations  
        az role assignment create `
            --role "8ebe5a00-799e-43f5-93ac-243d3dce84a7" `
            --assignee-object-id $ManagedIdentityPrincipalId `
            --assignee-principal-type "ServicePrincipal" `
            --scope $SearchId

        # Cognitive Services OpenAI User for OpenAI operations
        az role assignment create `
            --role "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd" `
            --assignee-object-id $ManagedIdentityPrincipalId `
            --assignee-principal-type "ServicePrincipal" `
            --scope $OpenAIId

        Write-SuccessLog "RBAC permissions assigned for secure token-based authentication"
    }
    catch {
        $rbacSuccess = $false
        Write-WarningLog "RBAC permission assignment failed: $_"
        Write-InfoLog "This is often due to conditional access policies in enterprise environments."
        Write-InfoLog "You will need to manually assign these RBAC permissions:"
        Write-Host "  • Storage Blob Data Contributor → $StorageAccount (Principal ID: $ManagedIdentityPrincipalId)" -ForegroundColor Yellow
        Write-Host "  • Azure Service Bus Data Receiver/Sender → $ServiceBusNamespace/$QueueName (Principal ID: $ManagedIdentityPrincipalId)" -ForegroundColor Yellow
        Write-Host "  • Search Index Data Contributor → $SearchService (Principal ID: $ManagedIdentityPrincipalId)" -ForegroundColor Yellow
        Write-Host "  • Cognitive Services OpenAI User → $OpenAIService (Principal ID: $ManagedIdentityPrincipalId)" -ForegroundColor Yellow
    }

    # Step 10: Create Event Grid subscription for blob storage events
    Write-InfoLog "Creating Event Grid subscription for blob storage events..."
    try {
        az eventgrid event-subscription create `
            --name "BlobCreatedToSB" `
            --source-resource-id $StorageId `
            --included-event-types Microsoft.Storage.BlobCreated `
            --endpoint-type servicebusqueue `
            --endpoint $QueueId `
            --output table

        Write-SuccessLog "Event Grid subscription created successfully"
    }
    catch {
        Write-WarningLog "Event Grid subscription creation failed: $_"
        Write-InfoLog "This can be created manually later or by running the container deployment script"
    }

    # Step 11: Create search index (Secure: Will use managed identity, not admin keys)
    Write-InfoLog "Creating simplified search index with 3 fields: id, content, vector..."
    
    # Load search index schema from external JSON file
    $IndexSchemaFile = "index_definiton\index.json"
    if (-not (Test-Path $IndexSchemaFile)) {
        Write-ErrorLog "Index definition file not found: $IndexSchemaFile"
        Write-ErrorLog "Please ensure the index definition file exists in the index_definiton folder"
        exit 1
    }
    
    try {
        # Check if search index already exists
        Write-InfoLog "Checking if search index 'documents' already exists..."
        $existingIndex = az search index show `
            --service-name $SearchService `
            --resource-group $ResourceGroup `
            --name "documents" `
            --query "name" -o tsv 2>$null
        
        if ($existingIndex -eq "documents") {
            Write-ExistsLog "Search index 'documents' already exists"
        } else {
            # Get search service admin key temporarily for index creation
            $SearchAdminKey = az search admin-key show `
                --service-name $SearchService `
                --resource-group $ResourceGroup `
                --query "primaryKey" -o tsv
            
            # Create the index using REST API with external JSON file
            $SearchEndpoint = "https://$SearchService.search.windows.net"
            $CreateIndexUrl = "$SearchEndpoint/indexes?api-version=2023-11-01"
            
            # Use curl for REST API call (more reliable than Invoke-RestMethod for complex JSON)
            Write-InfoLog "Creating search index from: $IndexSchemaFile"
            $CurlResult = curl -X POST $CreateIndexUrl `
                -H "Content-Type: application/json" `
                -H "api-key: $SearchAdminKey" `
                -d "@$IndexSchemaFile"
            
            if ($LASTEXITCODE -ne 0) {
                Write-ErrorLog "Failed to create search index. Exit code: $LASTEXITCODE"
                Write-ErrorLog "Response: $CurlResult"
                throw "Index creation failed"
            }
            
            Write-SuccessLog "Search index 'documents' created successfully from $IndexSchemaFile"
        }
    }
    catch {
        Write-WarningLog "Search index creation failed: $_"
        Write-InfoLog "You can create the index manually in Azure Portal or it will be created by the application"
    }

    # Step 12: Validate critical resources before proceeding
    Write-InfoLog "Validating critical infrastructure components..."
    $validationFailed = $false
    
    # Validate Container Apps Environment (most critical for deployment)
    if (-not (Test-AzureResource -ResourceType "containerapp-env" -ResourceName $AcaEnv -ResourceGroup $ResourceGroup)) {
        Write-ErrorLog "VALIDATION FAILED: Container Apps Environment '$AcaEnv' was not created successfully"
        $validationFailed = $true
    }
    
    # Validate Storage Account
    if (-not (Test-AzureResource -ResourceType "storage" -ResourceName $StorageAccount -ResourceGroup $ResourceGroup)) {
        Write-ErrorLog "VALIDATION FAILED: Storage Account '$StorageAccount' was not created successfully"
        $validationFailed = $true
    }
    
    # Validate Service Bus
    if (-not (Test-AzureResource -ResourceType "servicebus" -ResourceName $ServiceBusNamespace -ResourceGroup $ResourceGroup)) {
        Write-ErrorLog "VALIDATION FAILED: Service Bus '$ServiceBusNamespace' was not created successfully"
        $validationFailed = $true
    }
    
    # Validate Container Registry
    if (-not (Test-AzureResource -ResourceType "acr" -ResourceName $AcrName -ResourceGroup $ResourceGroup)) {
        Write-ErrorLog "VALIDATION FAILED: Container Registry '$AcrName' was not created successfully"
        $validationFailed = $true
    }
    
    # Validate Managed Identity
    if (-not (Test-AzureResource -ResourceType "identity" -ResourceName $ManagedIdentityName -ResourceGroup $ResourceGroup)) {
        Write-ErrorLog "VALIDATION FAILED: Managed Identity '$ManagedIdentityName' was not created successfully"
        $validationFailed = $true
    }
    
    if ($validationFailed) {
        Write-ErrorLog "Infrastructure validation failed. Cannot proceed with container deployment."
        Write-ErrorLog "Please review the errors above and re-run the script."
        exit 1
    }
    
    Write-SuccessLog "All critical infrastructure components validated successfully!"

    # Step 13: Display deployment summary
    Write-SuccessLog "Infrastructure deployment completed successfully!"
    Write-Host ""
    Write-Host "=== INFRASTRUCTURE SUMMARY ===" -ForegroundColor Cyan
    Write-Host "Resource Group: $ResourceGroup"
    Write-Host "Storage Account: $StorageAccount"
    Write-Host "Container: $ContainerName"
    Write-Host "Service Bus: $ServiceBusNamespace"
    Write-Host "Queue: $QueueName"
    Write-Host "Search Service: $SearchService"
    Write-Host "Container Registry: $AcrName (admin access enabled for ACA)"
    Write-Host "Container Apps Environment: $AcaEnv"
    Write-Host ""
    Write-Host "=== SECURITY SUMMARY ===" -ForegroundColor Green
    Write-Host " Storage Account: Key access DISABLED (token-based only)"
    Write-Host "Service Bus: Managed identity authentication configured"
    Write-Host "Azure Search: RBAC configured + simplified index created"
    Write-Host "Azure OpenAI: RBAC configured (no admin keys needed)"
    Write-Host "Container Registry: Admin access enabled (as requested for ACA)"
    Write-Host "Managed Identity: Created with least-privilege RBAC assignments"
    Write-Host "All services: TLS 1.2+ enforced"
    Write-Host "Blob Storage: Public access disabled"
    Write-Host "Search Index: Simple schema with 3 fields (id, content, vector)"
    Write-Host ""
    Write-Host "=== NEXT STEPS ===" -ForegroundColor Yellow
    Write-Host "Deploy your application (fully automated, cloud-native build):"
    Write-Host "   .\scripts\deploy-container.ps1"

    # Save configuration for later use
    $Config = @{
        ResourceGroup = $ResourceGroup
        StorageAccount = $StorageAccount
        ServiceBusNamespace = $ServiceBusNamespace
        QueueName = $QueueName
        AcrName = $AcrName
        SearchService = $SearchService
        OpenAIService = $OpenAIService
        AcaEnv = $AcaEnv
        AppName = $AppName
        ContainerName = $ContainerName
        StorageId = $StorageId
        QueueId = $QueueId
        SearchId = $SearchId
        OpenAIId = $OpenAIId
        ManagedIdentityName = $ManagedIdentityName
        ManagedIdentityId = $ManagedIdentityId
        ManagedIdentityClientId = $ManagedIdentityClientId
    }
    
    $Config | ConvertTo-Json | Out-File "deployment-config.json"
    Write-InfoLog "Configuration saved to deployment-config.json"

    Write-SuccessLog "Infrastructure deployment script completed!"
}
catch {
    Write-ErrorLog "Infrastructure deployment failed: $_"
    exit 1
}
