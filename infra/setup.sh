#!/usr/bin/env bash
# One-time Azure setup for Frase, following the course's deployment guide (steps 1-7 and 9).
# Run it once, by hand, before the first deploy; after that only the pipeline changes anything.
#
# Where: Azure Cloud Shell (Bash), which already has az, gh and sqlcmd. Sign in to GitHub first
# (gh auth login) so the script can store the GitHub secrets and variables itself; otherwise it
# prints what to add by hand.
#
#   LOCATION=<region> bash infra/setup.sh
#
# LOCATION must be one of the five regions your Azure for Students subscription allows; run the
# script without it to see the list. If the SQL free offer is not available there, set
# SQL_LOCATION to another region from the list (the SQL server may live in a different region).
#
# The script asks for three passwords and never prints them: the SQL admin's and one per service
# user. Use letters, digits, "-", "_" and "." only (at least 12 characters, with upper case, lower
# case and digits), so they can go into a connection string without escaping.
# Running it again is safe: whatever already exists is left as it is.

set -euo pipefail

PREFIX=aalsamara-ieu2024
RESOURCE_GROUP="rg-$PREFIX"
STORAGE_ACCOUNT=aalsamaraieu2024ui            # the prefix without hyphens, then "ui"
ENVIRONMENT="$PREFIX-env"
SQL_SERVER="$PREFIX-sql"
SQL_ADMIN=frase_admin
IDENTITY="$PREFIX-github"
SERVICES=(content scheduler)
GITHUB_REPO=Allaawii/devops_individual_assignment_1
GITHUB_REPO_IDS="Allaawii@206581026/devops_individual_assignment_1@1373375337"   # the numeric form of the subject
PLACEHOLDER_IMAGE=mcr.microsoft.com/k8se/quickstart:latest                     # replaced by the first deploy
PROFESSORS=(amartini@faculty.ie.edu bserra@faculty.ie.edu)

say() { printf '\n== %s\n' "$*"; }

exists() {                     # exists <az ... show command>: true if the resource is already there
  az "$@" --output none 2>/dev/null
}

ask_password() {               # ask_password <variable> <prompt>: read a password without echoing it
  local value
  read -rsp "$2: " value
  echo
  if [[ ! $value =~ ^[A-Za-z0-9._-]{12,}$ || ! $value =~ [A-Z] || ! $value =~ [a-z] || ! $value =~ [0-9] ]]; then
    echo "Use at least 12 characters from A-Z a-z 0-9 . _ - with upper case, lower case and digits." >&2
    exit 1
  fi
  printf -v "$1" '%s' "$value"
}

say "1. Subscription and region"
az account show --query "{subscription: name, id: id}" --output table
allowed=$(az policy assignment list \
  --query "[?displayName=='Allowed resource deployment regions'].parameters.listOfAllowedLocations.value | [0]" \
  --output tsv | tr '\t\n' '  ')
echo "regions this subscription allows: ${allowed:-(no region policy found)}"
if [[ -z ${LOCATION:-} ]]; then
  echo "Choose one and run again: LOCATION=<region> bash infra/setup.sh" >&2
  exit 1
fi
SQL_LOCATION=${SQL_LOCATION:-$LOCATION}
echo "using $LOCATION (SQL server: $SQL_LOCATION)"

ask_password SQL_ADMIN_PASSWORD "Password for the SQL admin ($SQL_ADMIN)"
ask_password CONTENT_PASSWORD "Password for the content service's database user"
ask_password SCHEDULER_PASSWORD "Password for the scheduler service's database user"

say "2. Providers and resource group $RESOURCE_GROUP"
for provider in Microsoft.App Microsoft.OperationalInsights Microsoft.Sql Microsoft.Storage Microsoft.ManagedIdentity; do
  az provider register --namespace "$provider" --wait --output none
done
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

say "3. The UI: storage account $STORAGE_ACCOUNT with a static website"
if ! exists storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP"; then
  az storage account create --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" \
    --kind StorageV2 --sku Standard_LRS --min-tls-version TLS1_2 --output none
fi
az storage blob service-properties update --account-name "$STORAGE_ACCOUNT" --auth-mode key \
  --static-website --index-document index.html --404-document index.html --output none
UI_URL=$(az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" \
  --query primaryEndpoints.web --output tsv)
UI_URL=${UI_URL%/}               # no trailing slash: this exact string is the CORS origin
echo "public URL: $UI_URL"

say "4. SQL server $SQL_SERVER and one serverless database per service (free offer)"
if ! exists sql server show --name "$SQL_SERVER" --resource-group "$RESOURCE_GROUP"; then
  az sql server create --name "$SQL_SERVER" --resource-group "$RESOURCE_GROUP" --location "$SQL_LOCATION" \
    --admin-user "$SQL_ADMIN" --admin-password "$SQL_ADMIN_PASSWORD" --output none
fi
az sql server firewall-rule create --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" \
  --name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 --output none
for service in "${SERVICES[@]}"; do
  database="$PREFIX-$service-db"
  if ! exists sql db show --name "$database" --server "$SQL_SERVER" --resource-group "$RESOURCE_GROUP"; then
    # The free offer fixes auto-pause (60 minutes) and the size (32 GB), so neither is passed.
    az sql db create --name "$database" --server "$SQL_SERVER" --resource-group "$RESOURCE_GROUP" \
      --edition GeneralPurpose --compute-model Serverless --family Gen5 --min-capacity 0.5 --capacity 1 \
      --backup-storage-redundancy Local --use-free-limit true --free-limit-exhaustion-behavior AutoPause \
      --output none
  fi
  az sql db show --name "$database" --server "$SQL_SERVER" --resource-group "$RESOURCE_GROUP" \
    --query "{database: name, autoPauseMinutes: autoPauseDelay, maxSizeBytes: maxSizeBytes, freeLimit: useFreeLimit}" \
    --output table
done

say "   One contained user per database, with only the rights the migrations need"
my_ip=$(curl -fsS https://api.ipify.org)            # this shell's public address
az sql server firewall-rule create --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" \
  --name setup-temporary --start-ip-address "$my_ip" --end-ip-address "$my_ip" --output none
trap 'az sql server firewall-rule delete --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" \
        --name setup-temporary --output none' EXIT      # the temporary rule goes, even on failure
export SQLCMDPASSWORD="$SQL_ADMIN_PASSWORD"             # sqlcmd reads the admin password from here
for service in "${SERVICES[@]}"; do
  user="${service}_svc"
  password_variable="${service^^}_PASSWORD"
  password="${!password_variable}"
  # A contained user lives inside its database only, so it cannot reach the other service's data.
  sqlcmd -S "tcp:$SQL_SERVER.database.windows.net,1433" -d "$PREFIX-$service-db" -U "$SQL_ADMIN" -b -Q "
    IF DATABASE_PRINCIPAL_ID(N'$user') IS NULL CREATE USER $user WITH PASSWORD = N'$password';
    ELSE ALTER USER $user WITH PASSWORD = N'$password';
    ALTER ROLE db_ddladmin ADD MEMBER $user;
    ALTER ROLE db_datareader ADD MEMBER $user;
    ALTER ROLE db_datawriter ADD MEMBER $user;
    GRANT REFERENCES ON SCHEMA::dbo TO $user;"
  echo "$user can use $PREFIX-$service-db"
done
unset SQLCMDPASSWORD

say "5. Container Apps environment $ENVIRONMENT and one Container App per service"
az extension add --name containerapp --upgrade --only-show-errors
if ! exists containerapp env show --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP"; then
  # Azure also creates a Log Analytics workspace for the containers' logs (part of the allowance).
  az containerapp env create --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" --output none
fi
for service in "${SERVICES[@]}"; do
  app="$PREFIX-$service"
  if ! exists containerapp show --name "$app" --resource-group "$RESOURCE_GROUP"; then
    az containerapp create --name "$app" --resource-group "$RESOURCE_GROUP" --environment "$ENVIRONMENT" \
      --image "$PLACEHOLDER_IMAGE" --ingress external --target-port 8000 \
      --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --output none
  fi
  echo "$app: https://$(az containerapp show --name "$app" --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.fqdn --output tsv)"
done

say "6. The pipeline's identity $IDENTITY: Contributor on $RESOURCE_GROUP only, signed in by GitHub (OIDC)"
if ! exists identity show --name "$IDENTITY" --resource-group "$RESOURCE_GROUP"; then
  az identity create --name "$IDENTITY" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --output none
fi
client_id=$(az identity show --name "$IDENTITY" --resource-group "$RESOURCE_GROUP" --query clientId --output tsv)
principal_id=$(az identity show --name "$IDENTITY" --resource-group "$RESOURCE_GROUP" --query principalId --output tsv)
group_id=$(az group show --name "$RESOURCE_GROUP" --query id --output tsv)
az role assignment create --assignee-object-id "$principal_id" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope "$group_id" --output none
# GitHub may name the repository by name or by numeric ids in the token's subject, so both are registered.
for subject in "repo:$GITHUB_REPO:ref:refs/heads/main" "repo:$GITHUB_REPO_IDS:ref:refs/heads/main"; do
  name="github-main-$(printf '%s' "$subject" | md5sum | cut -c1-8)"
  if ! exists identity federated-credential show --name "$name" --identity-name "$IDENTITY" --resource-group "$RESOURCE_GROUP"; then
    az identity federated-credential create --name "$name" --identity-name "$IDENTITY" \
      --resource-group "$RESOURCE_GROUP" --issuer https://token.actions.githubusercontent.com \
      --subject "$subject" --audiences api://AzureADTokenExchange --output none
  fi
  echo "trusts: $subject"
done

say "7. GitHub secrets and variables"
tenant_id=$(az account show --query tenantId --output tsv)
subscription_id=$(az account show --query id --output tsv)
if gh auth status > /dev/null 2>&1; then
  gh secret set AZURE_CLIENT_ID --repo "$GITHUB_REPO" --body "$client_id"
  gh secret set AZURE_TENANT_ID --repo "$GITHUB_REPO" --body "$tenant_id"
  gh secret set AZURE_SUBSCRIPTION_ID --repo "$GITHUB_REPO" --body "$subscription_id"
  gh secret set CONTENT_DB_PASSWORD --repo "$GITHUB_REPO" --body "$CONTENT_PASSWORD"
  gh secret set SCHEDULER_DB_PASSWORD --repo "$GITHUB_REPO" --body "$SCHEDULER_PASSWORD"
  gh variable set PREFIX --repo "$GITHUB_REPO" --body "$PREFIX"
  gh variable set RESOURCE_GROUP --repo "$GITHUB_REPO" --body "$RESOURCE_GROUP"
  gh variable set UI_STORAGE --repo "$GITHUB_REPO" --body "$STORAGE_ACCOUNT"
  echo "stored 5 secrets and 3 variables in $GITHUB_REPO"
else
  cat <<EOF
gh is not signed in, so add these by hand (GitHub: Settings > Secrets and variables > Actions):
  secrets:   AZURE_CLIENT_ID=$client_id  AZURE_TENANT_ID=$tenant_id  AZURE_SUBSCRIPTION_ID=$subscription_id
             CONTENT_DB_PASSWORD and SCHEDULER_DB_PASSWORD (the two service passwords you just typed)
  variables: PREFIX=$PREFIX  RESOURCE_GROUP=$RESOURCE_GROUP  UI_STORAGE=$STORAGE_ACCOUNT
EOF
fi
unset CONTENT_PASSWORD SCHEDULER_PASSWORD SQL_ADMIN_PASSWORD

say "9. Reader access on $RESOURCE_GROUP for the professors"
for professor in "${PROFESSORS[@]}"; do
  az role assignment create --assignee "$professor" --role Reader --scope "$group_id" --output none \
    && echo "Reader: $professor" || echo "Could not add $professor: add the Reader role in the portal (Access control)."
done

say "Done. Public URL: $UI_URL"
echo "Put it in system.yaml (public_url). The first deploy then fails once on purpose: make the two GHCR"
echo "packages (frase-content, frase-scheduler) public in GitHub, and re-run the failed job."
