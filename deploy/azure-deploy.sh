#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Azure Container Apps — Telecom Analyzer deployment script
# Run from project root:  bash deploy/azure-deploy.sh
# Requires: Azure CLI (az)  →  https://aka.ms/installazurecli
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Always run from project root (where Dockerfile lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Config — change these ────────────────────────────────────────────────────
RESOURCE_GROUP="telecom-analyzer-rg"
LOCATION="eastus"                        # az account list-locations -o table
ACR_NAME="telecomanalyzeracr$(date +%s)" # must be globally unique
APP_NAME="telecom-analyzer"
ENV_NAME="telecom-env"
IMAGE_TAG="latest"
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Telecom Analyzer — Azure Container Apps Deploy  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 1. Login
echo "▶ Step 1/6 — Azure login"
az login --output none
echo "   ✅ Logged in"

# 2. Resource group
echo "▶ Step 2/6 — Creating resource group: $RESOURCE_GROUP"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none
echo "   ✅ Resource group ready"

# 3. Container Registry
echo "▶ Step 3/6 — Creating Container Registry: $ACR_NAME"
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --output none
echo "   ✅ ACR created: ${ACR_NAME}.azurecr.io"

# 4. Build & push image via ACR Build (runs in Azure, no local Docker needed)
echo "▶ Step 4/6 — Building Docker image in Azure (this takes ~10-15 min first time)"
az acr build \
  --registry "$ACR_NAME" \
  --image "telecom-analyzer:${IMAGE_TAG}" \
  .
echo "   ✅ Image pushed: ${ACR_NAME}.azurecr.io/telecom-analyzer:${IMAGE_TAG}"

# 5. Container Apps Environment
echo "▶ Step 5/6 — Creating Container Apps environment"
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none
echo "   ✅ Environment ready"

# 6. Deploy Container App
echo "▶ Step 6/6 — Deploying container app"

ACR_PASSWORD=$(az acr credential show \
  --name "$ACR_NAME" \
  --query "passwords[0].value" \
  --output tsv)

az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "${ACR_NAME}.azurecr.io/telecom-analyzer:${IMAGE_TAG}" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --target-port 8501 \
  --ingress external \
  --cpu 2.0 \
  --memory 4.0Gi \
  --min-replicas 0 \
  --max-replicas 2 \
  --output none

APP_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   ✅  DEPLOYMENT COMPLETE                         ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║   URL : https://${APP_URL}"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "   Note: First cold start takes ~60s (scale-from-zero)."
echo "   Subsequent requests are fast."
echo ""
echo "   To redeploy after code changes:"
echo "   az acr build --registry $ACR_NAME --image telecom-analyzer:latest ."
echo "   az containerapp update --name $APP_NAME --resource-group $RESOURCE_GROUP \\"
echo "     --image ${ACR_NAME}.azurecr.io/telecom-analyzer:latest"
