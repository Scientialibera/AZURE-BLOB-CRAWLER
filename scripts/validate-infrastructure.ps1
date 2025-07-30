# Azure Infrastructure Validation Script for Container Apps Deployment
# This script validates that all required Azure resources are ready for ACA deployment

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

function Test-ResourceExists {
    param(
        [string]$ResourceId,
        [string]$ResourceName
    )
    
    try {
        $resource = az resource show --ids $ResourceId --output json 2>$null | ConvertFrom-Json
        if ($resource) {
            Write-SuccessLog "$ResourceName exists and is accessible"
            return $true
        }
    }
    catch {
        Write-ErrorLog "$ResourceName not found or not accessible"
        return $false
    }
    return $false
}

function Test-ContainerAppExists {
    param(
        [string]$AppName,
        [string]$ResourceGroup,
        [string]$Environment
    )
    
    try {
        $app = az containerapp show --name $AppName --resource-group $ResourceGroup --output json 2>$null | ConvertFrom-Json
        if ($app) {
            Write-SuccessLog "Container App '$AppName' exists"
            Write-InfoLog "App Status: $($app.properties.runningStatus)"
            Write-InfoLog "App URL: $($app.properties.configuration.ingress.fqdn)"
            return $true
        }
    }
    catch {
        Write-WarningLog "Container App '$AppName' not found in environment '$Environment'"
        return $false
    }
    return $false
}

function Test-AcrPermissions {
    param(
        [string]$AcrName,
        [string]$ResourceGroup
    )
    
    try {
        # Test if we can login to ACR
        az acr login --name $AcrName 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-SuccessLog "Successfully authenticated with ACR '$AcrName'"
            
            # Test if we can list repositories
            $repos = az acr repository list --name $AcrName --output json 2>$null | ConvertFrom-Json
            Write-InfoLog "ACR contains $($repos.Count) repositories"
            
            return $true
        } else {
            Write-ErrorLog "Failed to authenticate with ACR '$AcrName'"
            return $false
        }
    }
    catch {
        Write-ErrorLog "Error accessing ACR '$AcrName': $($_.Exception.Message)"
        return $false
    }
}

function Test-ContainerAppsEnvironment {
    param(
        [string]$Environment,
        [string]$ResourceGroup
    )
    
    try {
        $env = az containerapp env show --name $Environment --resource-group $ResourceGroup --output json 2>$null | ConvertFrom-Json
        if ($env) {
            Write-SuccessLog "Container Apps Environment '$Environment' exists"
            Write-InfoLog "Environment Status: $($env.properties.provisioningState)"
            
            # List apps in the environment
            $apps = az containerapp list --environment $Environment --resource-group $ResourceGroup --output json 2>$null | ConvertFrom-Json
            Write-InfoLog "Environment contains $($apps.Count) container apps"
            
            if ($apps.Count -gt 0) {
                Write-InfoLog "Existing apps:"
                foreach ($app in $apps) {
                    Write-InfoLog "  - $($app.name) (Status: $($app.properties.runningStatus))"
                }
            }
            
            return $true
        }
    }
    catch {
        Write-ErrorLog "Container Apps Environment '$Environment' not found or not accessible"
        return $false
    }
    return $false
}

function Test-ServiceBusQueue {
    param(
        [string]$Namespace,
        [string]$QueueName,
        [string]$ResourceGroup
    )
    
    try {
        $queue = az servicebus queue show --name $QueueName --namespace-name $Namespace --resource-group $ResourceGroup --output json 2>$null | ConvertFrom-Json
        if ($queue) {
            Write-SuccessLog "Service Bus Queue '$QueueName' exists in namespace '$Namespace'"
            Write-InfoLog "Queue Status: $($queue.status)"
            Write-InfoLog "Message Count: $($queue.messageCount)"
            return $true
        }
    }
    catch {
        Write-ErrorLog "Service Bus Queue '$QueueName' not found in namespace '$Namespace'"
        return $false
    }
    return $false
}

function Generate-LocalPushCommands {
    param(
        [string]$AcrName,
        [string]$AppName,
        [string]$ResourceGroup,
        [string]$Environment
    )
    
    Write-Host ""
    Write-Host "=== LOCAL IMAGE PUSH COMMANDS ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To build and push your local image to ACR:" -ForegroundColor Yellow
    Write-Host "cd src"
    Write-Host "docker build -t $AppName`:latest ."
    Write-Host "docker tag $AppName`:latest $AcrName.azurecr.io/$AppName`:latest"
    Write-Host "az acr login --name $AcrName"
    Write-Host "docker push $AcrName.azurecr.io/$AppName`:latest"
    Write-Host ""
    Write-Host "To create the Container App (if it doesn't exist):" -ForegroundColor Yellow
    Write-Host "az containerapp create ``"
    Write-Host "  --name $AppName ``"
    Write-Host "  --resource-group $ResourceGroup ``"
    Write-Host "  --environment $Environment ``"
    Write-Host "  --image $AcrName.azurecr.io/$AppName`:latest ``"
    Write-Host "  --target-port 50051 ``"
    Write-Host "  --ingress external ``"
    Write-Host "  --min-replicas 1 ``"
    Write-Host "  --max-replicas 3 ``"
    Write-Host "  --cpu 0.5 ``"
    Write-Host "  --memory 1Gi"
    Write-Host ""
    Write-Host "To update existing Container App:" -ForegroundColor Yellow
    Write-Host "az containerapp update ``"
    Write-Host "  --name $AppName ``"
    Write-Host "  --resource-group $ResourceGroup ``"
    Write-Host "  --image $AcrName.azurecr.io/$AppName`:latest"
}

# Error handling
$ErrorActionPreference = "Continue"

try {
    Write-InfoLog "Starting Azure infrastructure validation..."
    Write-Host ""

    # Check if Azure CLI is available and user is logged in
    if (!(Get-Command az -ErrorAction SilentlyContinue)) {
        Write-ErrorLog "Azure CLI is not installed. Please install it first."
        exit 1
    }

    try {
        az account show | Out-Null
    }
    catch {
        Write-ErrorLog "Not logged in to Azure. Please run 'az login' first."
        exit 1
    }

    Write-SuccessLog "Azure CLI verified and user is authenticated"

    # Load configuration
    if (!(Test-Path $ConfigFile)) {
        Write-ErrorLog "Configuration file '$ConfigFile' not found. Please run the infrastructure deployment script first."
        exit 1
    }

    $Config = Get-Content $ConfigFile | ConvertFrom-Json
    Write-SuccessLog "Configuration loaded from '$ConfigFile'"
    Write-InfoLog "Resource Group: $($Config.ResourceGroup)"
    Write-InfoLog "App Name: $($Config.AppName)"

    Write-Host ""
    Write-Host "=== INFRASTRUCTURE VALIDATION ===" -ForegroundColor Cyan

    # Validation results
    $ValidationResults = @{}

    # Test Resource Group
    Write-InfoLog "Validating Resource Group..."
    $rg = az group show --name $Config.ResourceGroup --output json 2>$null | ConvertFrom-Json
    if ($rg) {
        Write-SuccessLog "Resource Group '$($Config.ResourceGroup)' exists"
        $ValidationResults.ResourceGroup = $true
    } else {
        Write-ErrorLog "Resource Group '$($Config.ResourceGroup)' not found"
        $ValidationResults.ResourceGroup = $false
    }

    # Test Storage Account
    Write-InfoLog "Validating Storage Account..."
    $ValidationResults.StorageAccount = Test-ResourceExists -ResourceId $Config.StorageId -ResourceName "Storage Account '$($Config.StorageAccount)'"

    # Test Service Bus
    Write-InfoLog "Validating Service Bus..."
    $ValidationResults.ServiceBus = Test-ServiceBusQueue -Namespace $Config.ServiceBusNamespace -QueueName $Config.QueueName -ResourceGroup $Config.ResourceGroup

    # Test Search Service
    Write-InfoLog "Validating Search Service..."
    $ValidationResults.SearchService = Test-ResourceExists -ResourceId $Config.SearchId -ResourceName "Search Service '$($Config.SearchService)'"

    # Test OpenAI Service
    Write-InfoLog "Validating OpenAI Service..."
    $ValidationResults.OpenAIService = Test-ResourceExists -ResourceId $Config.OpenAIId -ResourceName "OpenAI Service '$($Config.OpenAIService)'"

    # Test Container Registry
    Write-InfoLog "Validating Container Registry..."
    $ValidationResults.ContainerRegistry = Test-AcrPermissions -AcrName $Config.AcrName -ResourceGroup $Config.ResourceGroup

    # Test Container Apps Environment
    Write-InfoLog "Validating Container Apps Environment..."
    $ValidationResults.ContainerAppsEnvironment = Test-ContainerAppsEnvironment -Environment $Config.AcaEnv -ResourceGroup $Config.ResourceGroup

    # Test if the specific app exists
    Write-InfoLog "Checking for Container App '$($Config.AppName)'..."
    $ValidationResults.ContainerApp = Test-ContainerAppExists -AppName $Config.AppName -ResourceGroup $Config.ResourceGroup -Environment $Config.AcaEnv

    Write-Host ""
    Write-Host "=== VALIDATION SUMMARY ===" -ForegroundColor Cyan
    
    $AllGood = $true
    foreach ($key in $ValidationResults.Keys) {
        $status = if ($ValidationResults[$key]) { "✓ PASS" } else { "✗ FAIL" }
        $color = if ($ValidationResults[$key]) { "Green" } else { "Red" }
        Write-Host "$key`: $status" -ForegroundColor $color
        
        if (!$ValidationResults[$key]) { $AllGood = $false }
    }

    Write-Host ""
    
    if ($AllGood -and $ValidationResults.ContainerApp) {
        Write-SuccessLog "All infrastructure components are ready and the Container App is deployed!"
        Write-InfoLog "You can update your app with a new image using the commands shown above."
    }
    elseif ($AllGood -and !$ValidationResults.ContainerApp) {
        Write-SuccessLog "All infrastructure components are ready, but the Container App '$($Config.AppName)' is not deployed yet."
        Write-InfoLog "You can deploy it using the commands shown below."
    }
    else {
        Write-WarningLog "Some infrastructure components are missing or not accessible."
        Write-InfoLog "Please check the failed components and re-run the infrastructure deployment if needed."
    }

    # Generate deployment commands
    Generate-LocalPushCommands -AcrName $Config.AcrName -AppName $Config.AppName -ResourceGroup $Config.ResourceGroup -Environment $Config.AcaEnv

    Write-Host ""
    Write-SuccessLog "Infrastructure validation completed!"

}
catch {
    Write-ErrorLog "Infrastructure validation failed: $_"
    exit 1
}
