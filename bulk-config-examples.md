# Bulk YAML Config Change Script - Examples

A practical guide for using `bulk-config-change.sh` with real DevOps scenarios.

## Table of Contents
1. [Kubernetes Deployment Examples](#kubernetes-deployment-examples)
2. [Docker Compose Examples](#docker-compose-examples)
3. [Helm Values Examples](#helm-values-examples)
4. [Multi-Environment Rollouts](#multi-environment-rollouts)
5. [Safety Tips](#safety-tips)

---

## Kubernetes Deployment Examples

### Example 1: Update Container Image Tag Across All Deployments

Rolling out a new application version to all deployments:

```bash
./bulk-config-change.sh \
  --path "k8s/deployments/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "registry.example.com/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")' \
  --dry-run
```

**What it does:**
- Finds all YAML files in `k8s/deployments/`
- Selects only `Deployment` kind resources
- Updates the first container's image tag to `v2.1.0`
- Uses `--dry-run` to preview changes first

**Real-world scenario:** Deploying a hotfix across 10 microservices simultaneously.

---

### Example 2: Scale Deployments to Handle Traffic Spike

Increase replicas for production deployments during peak hours:

```bash
./bulk-config-change.sh \
  --path "k8s/prod/**/*.yaml" \
  --key "spec.replicas" \
  --value "5" \
  --filter 'select(.kind == "Deployment" and .metadata.namespace == "production")'
```

**What it does:**
- Targets all YAML files in `k8s/prod/` subdirectories
- Filters for Deployments in the "production" namespace
- Sets replica count to 5

**Real-world scenario:** Auto-scaling configuration before a scheduled sales event.

---

### Example 3: Update CPU/Memory Limits for All Services

Adjust resource limits after profiling shows increased usage:

```bash
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "spec.template.spec.containers[0].resources.limits.memory" \
  --value "2Gi" \
  --filter 'select(.kind == "Deployment" or .kind == "StatefulSet")'

./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "spec.template.spec.containers[0].resources.limits.cpu" \
  --value "1000m" \
  --filter 'select(.kind == "Deployment" or .kind == "StatefulSet")'
```

**Real-world scenario:** Post-incident adjustment after CPU throttling issues.

---

### Example 4: Add Environment Variables to All Pods

Inject a global feature flag or configuration across all deployments:

```bash
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --operation "set-env" \
  --key "spec.template.spec.containers" \
  --env-key "FEATURE_FLAG_V2" \
  --env-value "enabled" \
  --filter 'select(.kind == "Deployment")'
```

**Real-world scenario:** Rolling out a beta feature to all services for testing.

---

### Example 5: Update Service Domain References

Change all references to the old domain across manifests:

```bash
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "spec.template.spec.containers[0].env[] | select(.name == \"API_URL\") | .value" \
  --value "https://api.newdomain.com" \
  --dry-run
```

---

## Docker Compose Examples

### Example 1: Update All Service Images for a Release

Promote staging images to production:

```bash
./bulk-config-change.sh \
  --path "docker-compose*.yaml" \
  --operation "set-env" \
  --key "services" \
  --env-key "ENVIRONMENT" \
  --env-value "production"
```

**Real-world scenario:** Switching environment configuration when promoting from staging to production.

---

### Example 2: Update Database Connection Strings

Migrate to a new database server across all services:

```bash
./bulk-config-change.sh \
  --path "docker-compose.yaml" \
  --operation "set-env" \
  --key "services" \
  --env-key "DATABASE_HOST" \
  --env-value "db-prod-02.internal:5432"
```

---

### Example 3: Add New Environment Variable to All Services

Enable debug logging globally:

```bash
./bulk-config-change.sh \
  --path "docker-compose.yaml" \
  --operation "set-env" \
  --key "services" \
  --env-key "LOG_LEVEL" \
  --env-value "DEBUG" \
  --dry-run

# After review, run without --dry-run
./bulk-config-change.sh \
  --path "docker-compose.yaml" \
  --operation "set-env" \
  --key "services" \
  --env-key "LOG_LEVEL" \
  --env-value "DEBUG"
```

---

## Helm Values Examples

### Example 1: Update Helm Chart Values for All Releases

Change configuration for all deployed Helm releases:

```bash
./bulk-config-change.sh \
  --path "helm/values*.yaml" \
  --key "image.tag" \
  --value "2.1.0"

./bulk-config-change.sh \
  --path "helm/values*.yaml" \
  --key "replicaCount" \
  --value "3"
```

**Real-world scenario:** Preparing Helm values for a batch release across multiple environments.

---

### Example 2: Enable Ingress for All Services

Activate ingress configuration:

```bash
./bulk-config-change.sh \
  --path "helm/values*.yaml" \
  --key "ingress.enabled" \
  --value "true"
```

---

## Multi-Environment Rollouts

### Complete Production Release Workflow

Rolling out version 2.1.0 to production with validation at each step:

```bash
# Step 1: Dry-run on dev
echo "=== DEV DRY-RUN ==="
./bulk-config-change.sh \
  --path "k8s/dev/**/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "myregistry.azurecr.io/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")' \
  --dry-run

# Step 2: Apply to dev
echo "=== Applying to DEV ==="
./bulk-config-change.sh \
  --path "k8s/dev/**/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "myregistry.azurecr.io/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")'

# Wait for validation...
read -p "Press enter after validating dev..."

# Step 3: Apply to staging
echo "=== Applying to STAGING ==="
./bulk-config-change.sh \
  --path "k8s/staging/**/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "myregistry.azurecr.io/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")'

# Step 4: Apply to production
echo "=== Applying to PRODUCTION ==="
./bulk-config-change.sh \
  --path "k8s/prod/**/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "myregistry.azurecr.io/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")'

echo "✓ Rollout complete!"
```

---

## Advanced Examples

### Example 1: Conditional Updates Based on Labels

Update only services labeled as "critical":

```bash
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "spec.replicas" \
  --value "3" \
  --filter 'select(.metadata.labels.tier == "critical")'
```

---

### Example 2: Batch Update Multiple Fields

Update multiple container environment variables:

```bash
# Update API endpoint
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --operation "set-env" \
  --key "spec.template.spec.containers" \
  --env-key "API_ENDPOINT" \
  --env-value "https://api-v2.example.com"

# Update API key
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --operation "set-env" \
  --key "spec.template.spec.containers" \
  --env-key "API_KEY" \
  --env-value "$(cat /run/secrets/api_key)"
```

---

### Example 3: Append to Existing Lists

Add annotations or labels to all resources:

```bash
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "metadata.labels" \
  --operation "append-list" \
  --value "version: v2.1.0" \
  --dry-run
```

---

## Safety Tips

### 1. **Always Use Dry-Run First**

```bash
# Always preview before applying
./bulk-config-change.sh --dry-run [OPTIONS]

# Compare output carefully
# Then run without --dry-run when confident
```

### 2. **Verify Backups Exist**

```bash
# Backups are created in .config-backups/ by default
ls -lah .config-backups/

# Restore if needed
cp .config-backups/deployment.yaml.backup.123456789 k8s/deployment.yaml
```

### 3. **Check File Count First**

```bash
# See how many files will be modified
ls k8s/**/*.yaml | wc -l

# Compare with script output
```

### 4. **Use Verbose Mode for Debugging**

```bash
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "spec.replicas" \
  --value "3" \
  --verbose \
  --dry-run
```

### 5. **Validate YAML After Changes**

```bash
# Check syntax of all modified files
for f in k8s/**/*.yaml; do yq eval '.' "$f" > /dev/null && echo "✓ $f" || echo "✗ $f"; done
```

### 6. **Version Control Integration**

```bash
# View changes before committing
git diff k8s/

# Commit with meaningful message
git commit -m "chore: update images to v2.1.0 across all deployments"
```

### 7. **Common Filter Patterns**

```bash
# Deployments only
--filter 'select(.kind == "Deployment")'

# Specific namespace
--filter 'select(.metadata.namespace == "production")'

# Multiple kinds
--filter 'select(.kind == "Deployment" or .kind == "StatefulSet")'

# By label
--filter 'select(.metadata.labels.app == "myapp")'

# Everything except a resource
--filter 'select(.kind != "ConfigMap")'

# Combine conditions
--filter 'select(.kind == "Deployment" and .metadata.namespace == "prod" and .metadata.labels.tier == "critical")'
```

---

## Troubleshooting

### "Invalid YAML syntax" Error

```bash
# Validate files manually
yq eval '.' problematic-file.yaml

# Check for tabs (YAML requires spaces)
cat -A problematic-file.yaml | grep "^I"
```

### Changes Not Applied

```bash
# Enable verbose mode
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --key "spec.replicas" \
  --value "3" \
  --verbose \
  --dry-run

# Verify filter syntax
yq eval '.kind' k8s/**/*.yaml  # Check actual kind values
```

### Glob Pattern Not Matching Files

```bash
# Enable globstar in bash
shopt -s globstar

# Test glob manually
ls k8s/**/*.yaml

# Or use absolute paths
./bulk-config-change.sh \
  --path "/absolute/path/k8s/**/*.yaml" \
  --key "spec.replicas" \
  --value "3"
```

---

## Performance Tips

- **Large directories:** Use specific patterns like `k8s/prod/` instead of `k8s/**/*`
- **Many files:** Run without `--verbose` for faster execution
- **Batch operations:** Combine related changes in a single script run

---

## Integration Examples

### GitHub Actions Workflow

```yaml
name: Update Config
on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Image tag to deploy'
        required: true

jobs:
  update-config:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install yq
        run: |
          sudo apt-get update
          sudo apt-get install -y yq
      
      - name: Update deployments
        run: |
          chmod +x ./scripts/bulk-config-change.sh
          ./scripts/bulk-config-change.sh \
            --path "k8s/**/*.yaml" \
            --key "spec.template.spec.containers[0].image" \
            --value "myregistry.azurecr.io/myapp:${{ github.event.inputs.image_tag }}" \
            --filter 'select(.kind == "Deployment")'
      
      - name: Create PR
        uses: peter-evans/create-pull-request@v4
        with:
          commit-message: "chore: update images to ${{ github.event.inputs.image_tag }}"
          title: "Update deployment images to ${{ github.event.inputs.image_tag }}"
          branch: "config-update/${{ github.event.inputs.image_tag }}"
```

---

## Success Indicators

✓ Script runs without errors
✓ Correct number of files processed
✓ Changes match dry-run preview
✓ Backups created successfully
✓ Updated YAML files validate without errors
✓ Version control shows expected diffs
