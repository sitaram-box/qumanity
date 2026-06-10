#!/usr/bin/env bash
# Alias — use fix_nocobase_admin.sh (correct camelCase rolesUsers SQL).
exec "$(dirname "$0")/fix_nocobase_admin.sh" "$@"
