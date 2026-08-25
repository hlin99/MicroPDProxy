#!/usr/bin/env bash
set -uo pipefail

max_retries="$1"
shift

for ((attempt = 0; attempt <= max_retries; attempt++)); do
  if "$@"; then
    exit 0
  else
    status=$?
  fi

  if ((attempt == max_retries)); then
    exit "${status}"
  fi

  retry=$((attempt + 1))
  echo "::warning::Command failed; retrying (${retry}/${max_retries}) in 5 seconds"
  sleep 5
done
