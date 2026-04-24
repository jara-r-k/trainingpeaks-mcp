#!/usr/bin/env bash
# attention-check.sh — Per-project attention detector for trainingpeaks-mcp.
# Emits JSON array of signal items per §6.2 schema.
# Reads scoring parameters from wiki/attention/thresholds.json.
#
# Part of the Attention Hub per-project detector layer (S4.4).
#
# Detectors:
#   1. Auth token expiry — checks keyring/config for freshness indicators
#   2. Test failures — runs pytest if tests/ exists
#   3. Uncommitted changes — counts uncommitted files
#   4. Stale branches — unmerged branches older than 30 days
#   5. Dependency age — checks pyproject.toml modification recency
#
# Output: JSON array to stdout. Logging to stderr.
set -uo pipefail

PROJECT="trainingpeaks-mcp"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECTS_ROOT="${PROJECTS_ROOT:-$(cd "${PROJECT_DIR}/.." && pwd)}"
THRESHOLDS_FILE="${PROJECTS_ROOT}/wiki/attention/thresholds.json"

# ---------- threshold helpers ----------

_tj() {
  python3 -c "
import json, sys
keys = sys.argv[2:]
with open(sys.argv[1]) as f:
    d = json.load(f)
for k in keys:
    d = d[k]
print(d)
" "$THRESHOLDS_FILE" "$@" 2>/dev/null
}

# Portable file mtime (works on both macOS and Linux).
_mtime() {
  python3 -c "import os,sys; print(int(os.path.getmtime(sys.argv[1])))" "$1" 2>/dev/null || echo "0"
}

score_to_band() {
  local s="$1"
  if (( s >= 80 )); then echo "critical"
  elif (( s >= 50 )); then echo "today"
  elif (( s >= 30 )); then echo "soon"
  else echo "ambient"
  fi
}

# ---------- JSON helpers ----------

json_escape() {
  python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$1"
}

emit_item() {
  local id="$1" source="$2" title="$3" body="$4" score="$5"
  local band; band=$(score_to_band "$score")
  local esc_title; esc_title=$(json_escape "$title")
  local esc_body; esc_body=$(json_escape "$body")
  cat <<ITEM
{"id":"${id}","source":"${source}","project":"${PROJECT}","title":${esc_title},"body":${esc_body},"score":${score},"band":"${band}"}
ITEM
}

items=()

# ========== DETECTOR 1: Auth token expiry ==========
# The project uses keyring-based auth (src/tp_mcp/auth/).
# Check for auth freshness indicators:
#   - .env or config files with token timestamps
#   - keyring storage files with modification times
#   - tp_auth_status MCP tool output cache

detect_auth() {
  >&2 echo "[attention] Checking auth token freshness..."

  local auth_stale=0
  local auth_body=""

  # Check for .env with token/auth hints
  if [[ -f "${PROJECT_DIR}/.env" ]]; then
    # Look for token expiry or timestamp fields
    local has_token; has_token=$(grep -ciE '(token|access_token|refresh_token|session|cookie)' "${PROJECT_DIR}/.env" 2>/dev/null || echo "0")
    if (( has_token > 0 )); then
      local env_age_days
      env_age_days=$(( ( $(date +%s) - $(_mtime "${PROJECT_DIR}/.env") ) / 86400 ))
      if (( env_age_days > 7 )); then
        auth_stale=1
        auth_body=".env with auth tokens last modified ${env_age_days}d ago"
      fi
    fi
  fi

  # Check keyring storage files for staleness
  local auth_dir="${PROJECT_DIR}/src/tp_mcp/auth"
  if [[ -d "$auth_dir" ]]; then
    # Look for any cached credential files in the project
    local cred_files
    cred_files=$(find "${PROJECT_DIR}" -maxdepth 3 \( -name "*.token" -o -name "*.cookie" -o -name "*.session" -o -name ".credentials" -o -name "auth_cache*" \) 2>/dev/null | head -5)
    if [[ -n "$cred_files" ]]; then
      while IFS= read -r cred_file; do
        local file_age_days
        file_age_days=$(( ( $(date +%s) - $(_mtime "$cred_file") ) / 86400 ))
        if (( file_age_days > 7 )); then
          auth_stale=1
          auth_body="Credential file $(basename "$cred_file") last refreshed ${file_age_days}d ago"
          break
        fi
      done <<< "$cred_files"
    fi
  fi

  # Check if tp_auth_status would report issues (look for cached status)
  local status_cache="${PROJECT_DIR}/.auth_status_cache"
  if [[ -f "$status_cache" ]]; then
    if grep -qi "expired\|invalid\|error" "$status_cache" 2>/dev/null; then
      auth_stale=1
      auth_body="Auth status cache reports expired or invalid session"
    fi
  fi

  if (( auth_stale )); then
    local score=55
    items+=("$(emit_item "tp:auth-stale" "trainingpeaks" \
      "${PROJECT}: auth token may be stale" "$auth_body" "$score")")
  fi
}

# ========== DETECTOR 2: Test failures ==========

detect_test_failures() {
  >&2 echo "[attention] Running test suite check..."

  if [[ ! -d "${PROJECT_DIR}/tests" ]]; then
    >&2 echo "[attention] No tests/ directory found, skipping."
    return
  fi

  local test_output
  local test_exit=0
  # Run pytest with a 60-second timeout to avoid hangs
  test_output=$(cd "$PROJECT_DIR" && timeout 60 python3 -m pytest tests/ --tb=no -q 2>/dev/null) || test_exit=$?

  if (( test_exit == 124 )); then
    # Timeout
    items+=("$(emit_item "tp:test-timeout" "ci" \
      "${PROJECT}: test suite timed out" "pytest timed out after 60s" "65")")
    return
  fi

  if (( test_exit != 0 )); then
    # Extract failure count from pytest summary line (e.g. "3 failed, 10 passed")
    local failed_count
    failed_count=$(echo "$test_output" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")
    local passed_count
    passed_count=$(echo "$test_output" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo "0")
    local error_count
    error_count=$(echo "$test_output" | grep -oE '[0-9]+ error' | grep -oE '[0-9]+' || echo "0")

    if [[ "$failed_count" == "0" && "$error_count" == "0" ]]; then
      failed_count=1  # At least 1 if exit code was non-zero
    fi

    local total_issues=$(( failed_count + error_count ))
    local score
    # Scale: 1 failure = 55 (today), 3+ = 70, 5+ = 85 (critical)
    if (( total_issues >= 5 )); then
      score=85
    elif (( total_issues >= 3 )); then
      score=70
    else
      score=55
    fi

    local body="${failed_count} failed, ${error_count} errors, ${passed_count} passed"
    items+=("$(emit_item "tp:test-failures" "ci" \
      "${PROJECT}: ${total_issues} test failure(s)" "$body" "$score")")
  fi
}

# ========== DETECTOR 3: Uncommitted changes ==========

detect_uncommitted() {
  >&2 echo "[attention] Checking uncommitted changes..."

  if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
    >&2 echo "[attention] Not a git repo, skipping."
    return
  fi

  local uncommitted_count
  uncommitted_count=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  if (( uncommitted_count > 0 )); then
    # Use thresholds from git.uncommitted_files
    local base; base=$(_tj git uncommitted_files base)
    local per_file; per_file=$(_tj git uncommitted_files per_file)
    local cap; cap=$(_tj git uncommitted_files cap)

    # Fallback if thresholds unavailable
    base=${base:-20}
    per_file=${per_file:-4}
    cap=${cap:-45}

    local score=$(( base + per_file * uncommitted_count ))
    (( score > cap )) && score=$cap

    local body="${uncommitted_count} uncommitted file(s) in working tree"
    items+=("$(emit_item "tp:uncommitted" "git" \
      "${PROJECT}: ${uncommitted_count} uncommitted files" "$body" "$score")")
  fi
}

# ========== DETECTOR 4: Stale branches ==========

detect_stale_branches() {
  >&2 echo "[attention] Checking for stale branches..."

  if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
    return
  fi

  local now_epoch
  now_epoch=$(date +%s)
  local default_branch
  default_branch=$(git -C "$PROJECT_DIR" symbolic-ref --short HEAD 2>/dev/null || echo "main")

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local branch_name; branch_name=$(echo "$line" | cut -d' ' -f1)
    local commit_epoch; commit_epoch=$(echo "$line" | cut -d' ' -f2)

    [[ "$branch_name" == "$default_branch" ]] && continue

    local days_old=$(( (now_epoch - commit_epoch) / 86400 ))
    if (( days_old >= 30 )); then
      # Score from thresholds
      local score=0
      if (( days_old >= 60 )); then
        score=$(_tj git stale_branch_days 60)
      else
        score=$(_tj git stale_branch_days 30)
      fi
      score=${score:-25}

      local tier
      if (( days_old >= 60 )); then tier=">60d"
      else tier=">30d"
      fi

      local body="Branch ${branch_name} last commit ${days_old}d ago (${tier})"
      items+=("$(emit_item "tp:stale-branch:${branch_name}" "git" \
        "${PROJECT}: stale branch ${branch_name} (${tier})" "$body" "$score")")
    fi
  done < <(git -C "$PROJECT_DIR" for-each-ref \
    --sort=committerdate \
    --format='%(refname:short) %(committerdate:unix)' \
    refs/heads/ 2>/dev/null)
}

# ========== DETECTOR 5: Dependency age ==========

detect_dependency_age() {
  >&2 echo "[attention] Checking dependency freshness..."

  local dep_file=""
  if [[ -f "${PROJECT_DIR}/pyproject.toml" ]]; then
    dep_file="${PROJECT_DIR}/pyproject.toml"
  elif [[ -f "${PROJECT_DIR}/requirements.txt" ]]; then
    dep_file="${PROJECT_DIR}/requirements.txt"
  fi

  if [[ -z "$dep_file" ]]; then
    >&2 echo "[attention] No dependency file found, skipping."
    return
  fi

  local file_mod_epoch
  file_mod_epoch=$(python3 -c "import os,sys; print(int(os.path.getmtime(sys.argv[1])))" "$dep_file" 2>/dev/null || echo "0")
  local now_epoch; now_epoch=$(date +%s)
  local days_old=$(( (now_epoch - file_mod_epoch) / 86400 ))

  # Score: >90 days = 35 (soon), >180 days = 50 (today), >365 = 65
  local score=0
  local body=""
  if (( days_old >= 365 )); then
    score=65
    body="$(basename "$dep_file") last modified ${days_old}d ago (>1 year) — dependencies may be significantly outdated"
  elif (( days_old >= 180 )); then
    score=50
    body="$(basename "$dep_file") last modified ${days_old}d ago (>6 months) — consider checking for updates"
  elif (( days_old >= 90 )); then
    score=35
    body="$(basename "$dep_file") last modified ${days_old}d ago (>90 days)"
  fi

  if (( score > 0 )); then
    items+=("$(emit_item "tp:deps-stale" "project" \
      "${PROJECT}: dependencies not updated in ${days_old}d" "$body" "$score")")
  fi
}

# ========== Run all detectors with error trapping ==========

run_detector() {
  local name="$1"
  local func="$2"
  if ! "$func" 2>&1 1>/dev/null | cat >&2; then
    # If the detector function itself fails, emit a signal about the failure
    items+=("$(emit_item "tp:detector-error:${name}" "project" \
      "${PROJECT}: ${name} detector failed" "The ${name} check encountered an error" "25")")
  fi
}

# Redirect stderr from detectors properly — run each, catch failures
for detector_pair in \
  "auth:detect_auth" \
  "tests:detect_test_failures" \
  "uncommitted:detect_uncommitted" \
  "stale-branches:detect_stale_branches" \
  "dependency-age:detect_dependency_age"; do

  name="${detector_pair%%:*}"
  func="${detector_pair##*:}"

  # Run detector; if it crashes, emit an error signal
  if ! "$func"; then
    >&2 echo "[attention] WARNING: ${name} detector failed"
    items+=("$(emit_item "tp:detector-error:${name}" "project" \
      "${PROJECT}: ${name} detector failed" "The ${name} check encountered an error" "25")")
  fi
done

# ---------- assemble JSON array ----------

if (( ${#items[@]} == 0 )); then
  echo '[]'
else
  printf '['
  for i in "${!items[@]}"; do
    (( i > 0 )) && printf ','
    printf '%s' "${items[$i]}"
  done
  printf ']\n'
fi
