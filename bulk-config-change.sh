#!/bin/bash

################################################################################
# Bulk YAML Configuration Change Script
#
# Purpose: Safely apply bulk changes to YAML configuration files (K8s manifests,
#          Docker Compose, Helm values, etc.) with dry-run, validation, and backup
#
# Requirements: yq (YAML processor), jq (optional, for advanced filtering)
#
# Usage Examples:
#   # Dry-run to preview changes
#   ./bulk-config-change.sh --dry-run --path "*.yaml" --key "image" --value "myapp:v2.0"
#
#   # Update all K8s manifests to new image tag
#   ./bulk-config-change.sh --path "k8s/**/*.yaml" \
#     --key "spec.template.spec.containers[0].image" \
#     --value "myregistry.azurecr.io/myapp:v2.1.0" \
#     --filter 'select(.kind == "Deployment")'
#
#   # Increase replicas across all deployments
#   ./bulk-config-change.sh --path "k8s/**/*.yaml" \
#     --key "spec.replicas" --value "3" \
#     --filter 'select(.kind == "Deployment")'
#
#   # Update environment variable in all services
#   ./bulk-config-change.sh --path "docker-compose*.yaml" \
#     --key "services.*.environment" --operation "set-env" \
#     --env-key "LOG_LEVEL" --env-value "DEBUG"
#
################################################################################

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script defaults
DRY_RUN=false
CREATE_BACKUP=true
BACKUP_DIR=".config-backups"
OPERATION="update"
FILTER=""
VERBOSE=false
CHANGES_MADE=0

################################################################################
# Functions
################################################################################

print_help() {
    cat << 'EOF'
Usage: bulk-config-change.sh [OPTIONS]

Required Options:
  --path PATH                 Glob pattern for YAML files (e.g., "*.yaml", "k8s/**/*.yaml")
  --key KEY_PATH              YAML path to update (dot notation, e.g., "spec.replicas")
  --value VALUE               New value to set

Optional Options:
  --filter EXPRESSION         YQ filter to select specific resources
                              (e.g., 'select(.kind == "Deployment")')

  --operation OP              Operation type: update|set-env|append-list|remove
                              Default: update

  --env-key KEY               Key for environment variable (for set-env operation)
  --env-value VALUE           Value for environment variable (for set-env operation)

  --dry-run                   Preview changes without modifying files
  --no-backup                 Skip creating backups
  --verbose                   Verbose output
  --help                      Show this help message

Examples:
  # Update image tag
  ./bulk-config-change.sh --path "k8s/*.yaml" \\
    --key "spec.template.spec.containers[0].image" \\
    --value "myapp:v2.0" \\
    --filter 'select(.kind == "Deployment")'

  # Update multiple replicas
  ./bulk-config-change.sh --path "k8s/**/*.yaml" \\
    --key "spec.replicas" --value "5" \\
    --filter 'select(.kind == "Deployment" or .kind == "StatefulSet")'

  # Update environment variable
  ./bulk-config-change.sh --path "docker-compose.yaml" \\
    --operation "set-env" \\
    --key "services" \\
    --env-key "DATABASE_URL" \\
    --env-value "postgres://prod-db:5432/mydb"

  # Append to list
  ./bulk-config-change.sh --path "k8s/values.yaml" \\
    --key "additionalLabels" --operation "append-list" \\
    --value "environment: production"

EOF
}

log_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

log_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

log_error() {
    echo -e "${RED}✗${NC}  $1"
}

# Check if required tools are installed
check_dependencies() {
    local missing_tools=()

    if ! command -v yq &> /dev/null; then
        missing_tools+=("yq")
    fi

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        echo ""
        echo "Install yq with:"
        echo "  # macOS"
        echo "  brew install yq"
        echo ""
        echo "  # Ubuntu/Debian"
        echo "  sudo apt-get install yq"
        echo ""
        echo "  # Or download from https://github.com/mikefarah/yq"
        exit 1
    fi
}

# Validate YAML syntax
validate_yaml() {
    local file="$1"
    if ! yq eval '.' "$file" > /dev/null 2>&1; then
        return 1
    fi
    return 0
}

# Create backup of file
backup_file() {
    local file="$1"

    if [[ "$CREATE_BACKUP" == true ]]; then
        mkdir -p "$BACKUP_DIR"
        local backup_file="$BACKUP_DIR/$(basename "$file").backup.$(date +%s)"
        cp "$file" "$backup_file"
        [[ "$VERBOSE" == true ]] && log_info "Backed up: $file → $backup_file"
    fi
}

# Apply a simple key-value update
apply_update() {
    local file="$1"
    local key_path="$2"
    local value="$3"

    # Build the yq command
    local yq_cmd="yq eval '${key_path} = \"${value}\"' -i '$file'"

    if [[ -n "$FILTER" ]]; then
        # Apply filter first, then update
        yq_cmd="yq eval '(${FILTER}) |= (${key_path} = \"${value}\")' -i '$file'"
    fi

    if [[ "$VERBOSE" == true ]]; then
        log_info "Executing: $yq_cmd"
    fi

    eval "$yq_cmd" || return 1
    return 0
}

# Set environment variable in services
apply_set_env() {
    local file="$1"
    local service_key="$2"
    local env_key="$3"
    local env_value="$4"

    local yq_cmd="yq eval '(${service_key}.*[] | select(type == \"!!map\")) |=
        (if .environment then
            .environment += [{\"${env_key}\": \"${env_value}\"}]
         else
            .environment = [{\"${env_key}\": \"${env_value}\"}]
         end)' -i '$file'"

    if [[ "$VERBOSE" == true ]]; then
        log_info "Executing set-env for $env_key=$env_value"
    fi

    eval "$yq_cmd" || return 1
    return 0
}

# Append item to list
apply_append_list() {
    local file="$1"
    local key_path="$2"
    local value="$3"

    local yq_cmd="yq eval '${key_path} += [\"${value}\"]' -i '$file'"

    if [[ "$VERBOSE" == true ]]; then
        log_info "Appending to ${key_path}: $value"
    fi

    eval "$yq_cmd" || return 1
    return 0
}

# Remove key from config
apply_remove() {
    local file="$1"
    local key_path="$2"

    local yq_cmd="yq eval 'del(${key_path})' -i '$file'"

    if [[ "$VERBOSE" == true ]]; then
        log_info "Removing: $key_path"
    fi

    eval "$yq_cmd" || return 1
    return 0
}

# Show diff preview in dry-run mode
show_preview() {
    local file="$1"
    local temp_file=$(mktemp)

    cp "$file" "$temp_file"

    # Apply change to temp file
    case "$OPERATION" in
        update)
            apply_update "$temp_file" "$KEY_PATH" "$VALUE" 2>/dev/null || true
            ;;
        set-env)
            apply_set_env "$temp_file" "$KEY_PATH" "$ENV_KEY" "$ENV_VALUE" 2>/dev/null || true
            ;;
        append-list)
            apply_append_list "$temp_file" "$KEY_PATH" "$VALUE" 2>/dev/null || true
            ;;
        remove)
            apply_remove "$temp_file" "$KEY_PATH" 2>/dev/null || true
            ;;
    esac

    # Show diff
    if ! diff -u "$file" "$temp_file" 2>/dev/null; then
        :  # diff returns 1 when files differ, which is expected
    fi

    rm "$temp_file"
}

# Process a single file
process_file() {
    local file="$1"

    # Validate YAML
    if ! validate_yaml "$file"; then
        log_error "Invalid YAML syntax in: $file"
        return 1
    fi

    log_info "Processing: $file"

    if [[ "$DRY_RUN" == true ]]; then
        log_info "DRY RUN - Preview of changes:"
        show_preview "$file"
        return 0
    fi

    # Create backup before modification
    backup_file "$file"

    # Apply the change
    case "$OPERATION" in
        update)
            if ! apply_update "$file" "$KEY_PATH" "$VALUE"; then
                log_error "Failed to update $file"
                return 1
            fi
            ;;
        set-env)
            if ! apply_set_env "$file" "$KEY_PATH" "$ENV_KEY" "$ENV_VALUE"; then
                log_error "Failed to set environment in $file"
                return 1
            fi
            ;;
        append-list)
            if ! apply_append_list "$file" "$KEY_PATH" "$VALUE"; then
                log_error "Failed to append to $file"
                return 1
            fi
            ;;
        remove)
            if ! apply_remove "$file" "$KEY_PATH"; then
                log_error "Failed to remove from $file"
                return 1
            fi
            ;;
        *)
            log_error "Unknown operation: $OPERATION"
            return 1
            ;;
    esac

    # Validate updated YAML
    if ! validate_yaml "$file"; then
        log_error "YAML validation failed after update: $file"
        return 1
    fi

    log_success "Updated: $file"
    ((CHANGES_MADE++))
    return 0
}

# Main processing loop
process_files() {
    local pattern="$1"
    local file_count=0
    local failed_count=0

    log_info "Finding files matching pattern: $pattern"

    # Use shopt to enable globstar (**) patterns
    shopt -s globstar 2>/dev/null || true

    for file in $pattern; do
        if [[ -f "$file" ]]; then
            ((file_count++))
            if ! process_file "$file"; then
                ((failed_count++))
            fi
        fi
    done

    echo ""
    log_info "Summary:"
    log_info "  Files processed: $file_count"
    log_info "  Changes made: $CHANGES_MADE"
    log_info "  Failed: $failed_count"

    if [[ "$DRY_RUN" == true ]]; then
        log_warn "DRY RUN MODE - No files were modified"
    fi

    if [[ "$CREATE_BACKUP" == true ]] && [[ $CHANGES_MADE -gt 0 ]]; then
        log_info "Backups stored in: $BACKUP_DIR"
    fi

    if [[ $failed_count -gt 0 ]]; then
        return 1
    fi
    return 0
}

################################################################################
# Main Script
################################################################################

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --path)
            FILE_PATTERN="$2"
            shift 2
            ;;
        --key)
            KEY_PATH="$2"
            shift 2
            ;;
        --value)
            VALUE="$2"
            shift 2
            ;;
        --filter)
            FILTER="$2"
            shift 2
            ;;
        --operation)
            OPERATION="$2"
            shift 2
            ;;
        --env-key)
            ENV_KEY="$2"
            shift 2
            ;;
        --env-value)
            ENV_VALUE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-backup)
            CREATE_BACKUP=false
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "${FILE_PATTERN:-}" ]]; then
    log_error "Missing required option: --path"
    print_help
    exit 1
fi

if [[ -z "${KEY_PATH:-}" ]]; then
    log_error "Missing required option: --key"
    print_help
    exit 1
fi

# Validate operation-specific requirements
case "$OPERATION" in
    update)
        if [[ -z "${VALUE:-}" ]]; then
            log_error "Operation 'update' requires --value"
            exit 1
        fi
        ;;
    set-env)
        if [[ -z "${ENV_KEY:-}" ]] || [[ -z "${ENV_VALUE:-}" ]]; then
            log_error "Operation 'set-env' requires --env-key and --env-value"
            exit 1
        fi
        ;;
    append-list)
        if [[ -z "${VALUE:-}" ]]; then
            log_error "Operation 'append-list' requires --value"
            exit 1
        fi
        ;;
    remove)
        # No additional requirements
        ;;
    *)
        log_error "Unknown operation: $OPERATION"
        exit 1
        ;;
esac

# Check dependencies
check_dependencies

# Main execution
log_info "=== Bulk YAML Configuration Change ==="
[[ "$DRY_RUN" == true ]] && log_warn "DRY RUN MODE (no changes will be made)"
echo ""

process_files "$FILE_PATTERN"
exit_code=$?

exit $exit_code
