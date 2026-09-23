#!/usr/bin/env bash
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$ROOT/stop.sh"
sleep 1
bash "$ROOT/start.sh"
