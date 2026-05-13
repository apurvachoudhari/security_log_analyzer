# Bulk Config Change Script - Quick Start Guide

## Installation & Setup

### Prerequisites

- `bash` (4.0+)
- `yq` (YAML query processor)

### Install yq

```bash
# macOS
brew install yq

# Ubuntu/Debian
sudo apt-get install yq

# Or download from GitHub
curl -sL https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -o /usr/local/bin/yq
chmod +x /usr/local/bin/yq
```

### Make Script Executable

```bash
chmod +x bulk-config-change.sh
```

---

## First Run: Test with Sample Files

### 1. Preview Changes (Dry-Run)

Try updating the sample Kubernetes deployment to a new image tag:

```bash
./bulk-config-change.sh \
  --path "sample-k8s-deployment.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "registry.example.com/web-app:v2.0.0" \
  --dry-run
```

**Expected output:**
```
ℹ  === Bulk YAML Configuration Change ===
ℹ  DRY RUN MODE (no changes will be made)

ℹ  Finding files matching pattern: sample-k8s-deployment.yaml
ℹ  Processing: sample-k8s-deployment.yaml
ℹ  DRY RUN - Preview of changes:
--- sample-k8s-deployment.yaml
+++ sample-k8s-deployment.yaml
@@ spec.template.spec.containers[0].image
- image: registry.example.com/web-app:v1.0.0
+ image: registry.example.com/web-app:v2.0.0

✓  Updated: sample-k8s-deployment.yaml

ℹ  Summary:
ℹ    Files processed: 1
ℹ    Changes made: 1
ℹ    Failed: 0
⚠  DRY RUN MODE - No files were modified
```

### 2. Apply the Change

Once you're happy with the preview, run without `--dry-run`:

```bash
./bulk-config-change.sh \
  --path "sample-k8s-deployment.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "registry.example.com/web-app:v2.0.0"
```

### 3. Verify the Change

```bash
# Check the updated file
grep -A 2 "image:" sample-k8s-deployment.yaml

# View the backup
ls -lah .config-backups/
```

---

## Common Use Cases

### Use Case 1: Update Container Image Across Multiple Deployments

**Scenario:** You need to deploy version `v2.1.0` of your application across all production deployments.

```bash
# 1. Preview
./bulk-config-change.sh \
  --path "k8s/prod/**/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "myregistry.azurecr.io/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")' \
  --dry-run

# 2. Review output carefully

# 3. Apply
./bulk-config-change.sh \
  --path "k8s/prod/**/*.yaml" \
  --key "spec.template.spec.containers[0].image" \
  --value "myregistry.azurecr.io/myapp:v2.1.0" \
  --filter 'select(.kind == "Deployment")'
```

---

### Use Case 2: Scale Services for Increased Load

**Scenario:** You need to increase replicas from 2 to 5 for all production deployments.

```bash
# 1. Preview
./bulk-config-change.sh \
  --path "k8s/prod/**/*.yaml" \
  --key "spec.replicas" \
  --value "5" \
  --filter 'select(.kind == "Deployment")' \
  --dry-run

# 2. Apply
./bulk-config-change.sh \
  --path "k8s/prod/**/*.yaml" \
  --key "spec.replicas" \
  --value "5" \
  --filter 'select(.kind == "Deployment")'
```

---

### Use Case 3: Update Environment Variables in Docker Compose

**Scenario:** You need to update the `LOG_LEVEL` to `DEBUG` for all services in docker-compose.yaml.

```bash
# 1. Preview
./bulk-config-change.sh \
  --path "sample-docker-compose.yaml" \
  --operation "set-env" \
  --key "services" \
  --env-key "LOG_LEVEL" \
  --env-value "DEBUG" \
  --dry-run

# 2. Apply
./bulk-config-change.sh \
  --path "sample-docker-compose.yaml" \
  --operation "set-env" \
  --key "services" \
  --env-key "LOG_LEVEL" \
  --env-value "DEBUG"
```

---

### Use Case 4: Change Database Connection String Globally

**Scenario:** You need to update the `DATABASE_HOST` across all Kubernetes manifests.

```bash
# 1. Preview
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --operation "set-env" \
  --key "spec.template.spec.containers" \
  --env-key "DATABASE_HOST" \
  --env-value "postgres-prod.internal:5432" \
  --dry-run

# 2. Apply
./bulk-config-change.sh \
  --path "k8s/**/*.yaml" \
  --operation "set-env" \
  --key "spec.template.spec.containers" \
  --env-key "DATABASE_HOST" \
  --env-value "postgres-prod.internal:5432"
```

---

## Safety Checklist

Before running any changes:

- [ ] **Use `--dry-run` first** to preview changes
- [ ] **Verify the file count** matches expectations
- [ ] **Check the diff** carefully in dry-run output
- [ ] **Have a backup strategy** (script auto-creates backups)
- [ ] **Test in dev/staging first** before production
- [ ] **Have a rollback plan** (backups are stored in `.config-backups/`)

---

## Restore from Backup

If something goes wrong:

```bash
# List available backups
ls -lah .config-backups/

# Restore a specific file
cp .config-backups/deployment.yaml.backup.1234567890 k8s/deployment.yaml

# Restore all backups from a specific date
for f in .config-backups/*.backup.1234567890; do
  original=$(basename "$f" | sed 's/.backup.*//')
  cp "$f" "$original"
done
```

---

## Understanding Filters

Filters help you select specific resources. Here are common patterns:

```bash
# Only Deployments
'select(.kind == "Deployment")'

# Only specific namespace
'select(.metadata.namespace == "production")'

# Multiple resource types
'select(.kind == "Deployment" or .kind == "StatefulSet")'

# By label
'select(.metadata.labels.tier == "critical")'

# Exclude certain kinds
'select(.kind != "ConfigMap")'

# Complex conditions
'select(.kind == "Deployment" and .metadata.namespace == "prod")'
```

---

## Getting Help

### View Full Usage
```bash
./bulk-config-change.sh --help
```

### Enable Verbose Output
```bash
./bulk-config-change.sh \
  --path "sample-k8s-deployment.yaml" \
  --key "spec.replicas" \
  --value "3" \
  --verbose \
  --dry-run
```

### Check YAML Syntax Manually
```bash
yq eval '.' your-file.yaml
```

### View Specific Fields
```bash
# List all Deployment names
yq eval '.metadata.name | select(. != null)' k8s/**/*.yaml

# List all image tags
yq eval '.spec.template.spec.containers[].image' k8s/**/*.yaml
```

---

## Common Errors & Solutions

### Error: "Invalid YAML syntax in: filename.yaml"

The YAML file has syntax errors. Check it manually:
```bash
yq eval '.' problematic-file.yaml
```

### Error: "Missing required tool: yq"

Install yq:
```bash
brew install yq  # macOS
sudo apt-get install yq  # Linux
```

### Filter not matching any files

Verify the filter syntax and resource kinds:
```bash
# Check what kinds exist in your files
yq eval '.kind' k8s/**/*.yaml

# Test filter manually
yq eval 'select(.kind == "Deployment")' k8s/deployment.yaml
```

### Changes not applied

1. Check that files exist: `ls k8s/**/*.yaml`
2. Use `--verbose` to see what's happening
3. Verify the YAML path is correct

---

## Next Steps

1. **Read the full examples:** See `bulk-config-examples.md`
2. **Integrate with CI/CD:** Use in GitHub Actions or similar
3. **Create custom scripts:** Wrap the script for your specific workflows
4. **Test extensively:** Always use `--dry-run` in production environments

---

## Performance Tips

- Use specific patterns like `k8s/prod/**/*.yaml` instead of broad globbing
- For large directories (1000+ files), remove `--verbose` for faster runs
- Process non-critical resources first to build confidence

---

## File Reference

- **bulk-config-change.sh** - Main script
- **bulk-config-examples.md** - Comprehensive examples for common scenarios
- **sample-k8s-deployment.yaml** - Test file: Kubernetes manifests
- **sample-docker-compose.yaml** - Test file: Docker Compose
- **QUICKSTART.md** - This file

---

Good luck with your bulk configuration changes! 🚀
