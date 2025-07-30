# Cleanup script for Azure Event-Driven File Processing Pipeline (PowerShell)
# This script removes all resources created by the deployment

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroup,
    
    [switch]$Force
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
    Write-InfoLog "Cleaning up Azure Event-Driven File Processing Pipeline"
    Write-InfoLog "Resource Group: $ResourceGroup"

    # Check if resource group exists
    $rgExists = az group exists --name $ResourceGroup
    if ($rgExists -eq "false") {
        Write-WarningLog "Resource group '$ResourceGroup' does not exist."
        exit 0
    }

    # List resources in the group
    Write-InfoLog "Listing resources in resource group..."
    $resources = az resource list --resource-group $ResourceGroup --query "[].{Name:name, Type:type}" -o table
    Write-Host $resources

    if (!$Force) {
        Write-Host ""
        Write-WarningLog "This will DELETE ALL resources in the resource group '$ResourceGroup'."
        $confirmation = Read-Host "Are you sure you want to continue? (yes/no)"
        
        if ($confirmation -ne "yes") {
            Write-InfoLog "Cleanup cancelled by user."
            exit 0
        }
    }

    # Delete the entire resource group
    Write-InfoLog "Deleting resource group and all contained resources..."
    Write-WarningLog "This operation may take several minutes..."
    
    az group delete --name $ResourceGroup --yes --no-wait

    Write-SuccessLog "Resource group deletion initiated."
    Write-InfoLog "The deletion is running in the background and may take several minutes to complete."
    Write-InfoLog "You can check the status in the Azure Portal or by running:"
    Write-Host "az group show --name $ResourceGroup" -ForegroundColor Yellow
    
    Write-SuccessLog "Cleanup script completed!"
}
catch {
    Write-ErrorLog "Cleanup failed: $_"
    exit 1
}
