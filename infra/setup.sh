#!/usr/bin/env bash
# One-time Azure setup for Frase. Run it once, by hand, before the first deploy; after that only
# the pipeline changes anything. Everything is created in the class resource group, and every
# name starts with the student prefix, so nothing of another student's is touched.
#
# Where to run it: Azure Cloud Shell (Bash), which already has az and sqlcmd, or any bash shell
# with the Azure CLI and sqlcmd installed. Sign in first with your IE account: az login
#
#   bash infra/setup.sh
#
# The script asks for three passwords and never prints them: the SQL admin's and one per service
# login. Use letters, digits, "-", "_" and "." only (at least 12 characters, with upper case, lower
# case and digits), so they can go into a DATABASE_URL without escaping.
# Running it again is safe: whatever already exists is left as it is.

set -euo pipefail

PREFIX=aalsamar-ieu2024
RESOURCE_GROUP=rg-sdd-3b
ENVIRONMENT="$PREFIX-env"
SQL_SERVER="$PREFIX-sql"
SQL_ADMIN=frase_admin
STATIC_WEB_APP="$PREFIX-ui"
SWA_LOCATION=westeurope        # Static Web Apps exist in only a few regions
SERVICES=(content scheduler)
PLACEHOLDER_IMAGE=mcr.microsoft.com/k8se/quickstart:latest   # replaced by the first deploy

LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)

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

ask_password SQL_ADMIN_PASSWORD "Password for the SQL admin ($SQL_ADMIN)"
ask_password CONTENT_PASSWORD "Password for the content_svc login"
ask_password SCHEDULER_PASSWORD "Password for the scheduler_svc login"

say "1. Container Apps environment $ENVIRONMENT (Consumption; creates its Log Analytics workspace)"
az extension add --name containerapp --upgrade --only-show-errors
if ! exists containerapp env show --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP"; then
  az containerapp env create --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" --output none
fi

say "2. SQL logical server $SQL_SERVER, reachable from Azure services only"
if ! exists sql server show --name "$SQL_SERVER" --resource-group "$RESOURCE_GROUP"; then
  az sql server create --name "$SQL_SERVER" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" \
    --admin-user "$SQL_ADMIN" --admin-password "$SQL_ADMIN_PASSWORD" --output none
fi
az sql server firewall-rule create --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" \
  --name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 --output none

say "3. One serverless database per service"
for service in "${SERVICES[@]}"; do
  database="$PREFIX-$service-db"
  if ! exists sql db show --name "$database" --server "$SQL_SERVER" --resource-group "$RESOURCE_GROUP"; then
    az sql db create --name "$database" --server "$SQL_SERVER" --resource-group "$RESOURCE_GROUP" \
      --edition GeneralPurpose --compute-model Serverless --family Gen5 \
      --min-capacity 0.5 --capacity 1 --auto-pause-delay 15 \
      --max-size 2GB --backup-storage-redundancy Local --output none
  fi
  echo "$database: auto-pause after $(az sql db show --name "$database" --server "$SQL_SERVER" \
    --resource-group "$RESOURCE_GROUP" --query autoPauseDelay --output tsv) minutes"
done

say "4. One login per service, each db_owner of its own database only"
my_ip=$(curl -fsS https://api.ipify.org)            # this shell's public address
az sql server firewall-rule create --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" \
  --name setup-temporary --start-ip-address "$my_ip" --end-ip-address "$my_ip" --output none
trap 'az sql server firewall-rule delete --resource-group "$RESOURCE_GROUP" --server "$SQL_SERVER" \
        --name setup-temporary --output none' EXIT      # the temporary rule goes, even on failure

export SQLCMDPASSWORD="$SQL_ADMIN_PASSWORD"             # sqlcmd reads the password from here
run_sql() {                    # run_sql <database> <sql>
  sqlcmd -S "tcp:$SQL_SERVER.database.windows.net,1433" -d "$1" -U "$SQL_ADMIN" -b -Q "$2"
}
for service in "${SERVICES[@]}"; do
  login="${service}_svc"
  password_variable="${service^^}_PASSWORD"
  password="${!password_variable}"
  run_sql master "IF SUSER_ID(N'$login') IS NULL CREATE LOGIN $login WITH PASSWORD = N'$password';
                  ELSE ALTER LOGIN $login WITH PASSWORD = N'$password';"
  run_sql "$PREFIX-$service-db" "IF USER_ID(N'$login') IS NULL CREATE USER $login FOR LOGIN $login;
                                  ALTER ROLE db_owner ADD MEMBER $login;"
  echo "$login can use $PREFIX-$service-db"
done
unset SQLCMDPASSWORD

say "5. One Container App per service: external HTTPS, scale 0 to 1"
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

say "6. Static Web App $STATIC_WEB_APP (Free plan)"
if ! exists staticwebapp show --name "$STATIC_WEB_APP" --resource-group "$RESOURCE_GROUP"; then
  az staticwebapp create --name "$STATIC_WEB_APP" --resource-group "$RESOURCE_GROUP" \
    --location "$SWA_LOCATION" --sku Free --output none
fi
echo "public URL: https://$(az staticwebapp show --name "$STATIC_WEB_APP" --resource-group "$RESOURCE_GROUP" \
  --query defaultHostname --output tsv)"

say "Done. Add these four secrets in GitHub (Settings > Secrets and variables > Actions):"
cat <<EOF
  AZURE_CREDENTIALS       the class service principal JSON from the professor
  SWA_DEPLOYMENT_TOKEN    the output of:
                            az staticwebapp secrets list --name $STATIC_WEB_APP --query properties.apiKey -o tsv
  CONTENT_DATABASE_URL    mssql://content_svc:<content password>@$SQL_SERVER.database.windows.net:1433/$PREFIX-content-db
  SCHEDULER_DATABASE_URL  mssql://scheduler_svc:<scheduler password>@$SQL_SERVER.database.windows.net:1433/$PREFIX-scheduler-db
After the first deploy, make the two GHCR packages (frase-content, frase-scheduler) public, so the
Container Apps can pull them without a registry password.
EOF
