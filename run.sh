#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-d" ]]; then
  docker compose up --build -d
else
  docker compose up --build
fi

