#!/usr/bin/env bash
# Create every Azure resource the project uses, from nothing, each after the ones it needs.
#
# Run once, logged in with `az login`, on a subscription where the names below are free.
# Left to other files: the data, landed by src/motrisk/fetch.py and extracted by
# src/motrisk/extract.py, both run on the virtual machine (see the end of this file), and the
# Function's code, deployed by function/publish.sh.
# Everything this script creates sits in one resource group, so one command removes it all:
#     az group delete --name rg-mot-failure-risk
# Azure itself adds a second group, NetworkWatcherRG, when the virtual machine's network is
# created, holding a Network Watcher for the machine's region. The command above leaves it, and
#     az group delete --name NetworkWatcherRG
# removes it as well.
set -euo pipefail

GROUP=rg-mot-failure-risk
REGION=northeurope       # the storage account, the logs and the Function
VM_REGION=swedencentral  # the nearest region offering this subscription small virtual machines
ACCOUNT=stmotrisk
CONTAINER=raw            # the files as published
CSV_CONTAINER=csv        # the CSVs extracted from them
VM=vm-motrisk
WORKSPACE=log-motrisk
APP=func-motrisk
ROLE="Storage Blob Data Contributor"

# 1. Let the subscription create storage, machines and their networks, Functions, and logs.
for namespace in Microsoft.Storage Microsoft.Compute Microsoft.Network Microsoft.Web \
    Microsoft.Insights Microsoft.OperationalInsights; do
    az provider register --namespace "$namespace" --wait
done

# 2. The group, the storage account and its two containers. The containers are created through
#    Azure's management API, which needs no data role, so they do not wait for step 3's role to
#    take effect.
az group create --name "$GROUP" --location "$REGION" --output none
az storage account create --resource-group "$GROUP" --name "$ACCOUNT" --location "$REGION" \
    --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
    --allow-blob-public-access false --output none
for container in "$CONTAINER" "$CSV_CONTAINER"; do
    az storage container-rm create --resource-group "$GROUP" --storage-account "$ACCOUNT" \
        --name "$container" --output none
done
account_id=$(az storage account show --resource-group "$GROUP" --name "$ACCOUNT" --query id -o tsv)

# 3. The data role for whoever runs this script: Owner manages the account but cannot read its
#    files. A new role takes a few minutes to take effect.
me=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --role "$ROLE" --assignee "$me" --scope "$account_id" --output none

# 4. The virtual machine that lands the 17 files and extracts their CSVs, with its own identity,
#    then that identity's data role. The role is a separate command: `az vm create --role` fails
#    for a data role.
az vm create --resource-group "$GROUP" --name "$VM" --location "$VM_REGION" \
    --image Ubuntu2404 --size Standard_B2ats_v2 --admin-username azureuser \
    --generate-ssh-keys --assign-identity --output none
vm_principal=$(az vm show --resource-group "$GROUP" --name "$VM" \
    --query identity.principalId -o tsv)
az role assignment create --role "$ROLE" --assignee-object-id "$vm_principal" \
    --assignee-principal-type ServicePrincipal --scope "$account_id" --output none

# 5. The workspace where Application Insights keeps the Function's logs. Without it, the CLI
#    would pick or create one in a resource group of its own, outside this one.
az monitor log-analytics workspace create --resource-group "$GROUP" --name "$WORKSPACE" \
    --location "$REGION" --output none

# 6. The Function App on the Flex Consumption plan, with its own identity, then that identity's
#    data role. Creating it also creates its plan, its Application Insights and, in the storage
#    account, the containers the Functions runtime keeps its own files in.
az functionapp create --resource-group "$GROUP" --name "$APP" --storage-account "$ACCOUNT" \
    --flexconsumption-location "$REGION" --runtime python --runtime-version 3.12 \
    --workspace "$WORKSPACE" --assign-identity '[system]' --output none
app_principal=$(az functionapp identity show --resource-group "$GROUP" --name "$APP" \
    --query principalId -o tsv)
az role assignment create --role "$ROLE" --assignee-object-id "$app_principal" \
    --assignee-principal-type ServicePrincipal --scope "$account_id" --output none

echo "Created $GROUP: $ACCOUNT/$CONTAINER and $ACCOUNT/$CSV_CONTAINER, $VM, $WORKSPACE and $APP."

# Then, by hand:
#
# Land the 17 files from the virtual machine, then extract their CSVs into the container csv.
# Start the machine if it is deallocated, and copy the repository to it, from the laptop:
#     az vm start --resource-group rg-mot-failure-risk --name vm-motrisk
#     ip=$(az vm show --show-details --resource-group rg-mot-failure-risk --name vm-motrisk \
#         --query publicIps -o tsv)
#     rsync -av --exclude data/raw --exclude data/extracted --exclude .venv --exclude .git \
#         --exclude '*.egg-info' ./ "azureuser@$ip:mot-failure-risk/"
# then, on the machine (ssh "azureuser@$ip"), inside tmux so the run survives a dropped connection:
#     sudo apt-get update && sudo apt-get install -y python3-venv tmux
#     cd mot-failure-risk && python3 -m venv .venv && source .venv/bin/activate && pip install -e .
#     python -u src/motrisk/fetch.py 2>&1 | tee fetch.log
#     python -u src/motrisk/extract.py azure 2>&1 | tee extract.log
# and stop paying for its processor once it is done:
#     az vm deallocate --resource-group rg-mot-failure-risk --name vm-motrisk
#
# Deploy the watcher:
#     ./function/publish.sh
