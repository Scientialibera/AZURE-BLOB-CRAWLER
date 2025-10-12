# GitHub Actions Workflows

## CI/CD Pipeline

The `ci-cd.yml` workflow automates testing, building, and deployment of both services.

### Workflow Triggers

- **Push to `main`**: Runs tests, builds images, pushes to ACR, and deploys to Container Apps
- **Push to `develop`**: Runs tests only (no deployment)
- **Pull Requests to `main`**: Runs tests only

### Required GitHub Secrets

Configure these secrets in your repository settings (Settings → Secrets and variables → Actions):

| Secret Name | Description | Example |
|------------|-------------|---------|
| `AZURE_CREDENTIALS` | Azure service principal credentials (JSON) | See below |
| `AZURE_REGISTRY` | Azure Container Registry name (without .azurecr.io) | `myregistry` |
| `AZURE_RESOURCE_GROUP` | Resource group containing Container Apps | `rg-blob-crawler` |
| `INDEXER_APP_NAME` | Indexer Container App name | `indexer-app` |
| `MCP_SERVER_APP_NAME` | MCP Server Container App name | `mcp-server` |

### Setting up AZURE_CREDENTIALS

Create a service principal with contributor access to your resource group:

```bash
az ad sp create-for-rbac \
  --name "github-actions-blob-crawler" \
  --role contributor \
  --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group-name} \
  --sdk-auth
```

Copy the entire JSON output and add it as the `AZURE_CREDENTIALS` secret.

### Workflow Jobs

1. **test-indexer** - Runs linting and tests for indexer service
2. **test-mcp** - Runs linting and tests for MCP server
3. **build-and-push-indexer** - Builds Docker image, pushes to ACR, updates Container App (only on main branch)
4. **build-and-push-mcp** - Builds Docker image, pushes to ACR, updates Container App (only on main branch)
5. **notify-deployment** - Creates deployment summary with service URLs

### Health Checks

After deployment, the workflow verifies that both services are healthy by checking their `/health` endpoints. If a health check fails, the deployment job fails.

### Viewing Results

- **Workflow runs**: Actions tab in GitHub
- **Deployment summary**: Each successful deployment shows service URLs in the job summary
- **Container logs**: Azure Portal → Container Apps → Log stream

### Local Testing

Run tests locally before pushing:

```bash
# Test indexer
cd services/indexer_app
pip install -r requirements-test.txt
pytest tests/ -v

# Test MCP server
cd services/mcp_server
pip install -r requirements-test.txt
pytest tests/ -v

# Linting
flake8 app/ --count --max-line-length=127 --statistics
```

### Troubleshooting

**Workflow fails at Azure login:**
- Verify `AZURE_CREDENTIALS` secret is valid
- Check service principal has required permissions

**Workflow fails at ACR login:**
- Verify `AZURE_REGISTRY` secret matches your ACR name
- Ensure service principal has AcrPush role

**Deployment succeeds but health check fails:**
- Check Container App logs in Azure Portal
- Verify environment variables are set correctly
- Check managed identity permissions

**Tests fail:**
- Run tests locally to reproduce
- Check that all dependencies are in requirements.txt
- Verify Python version (3.11+)
