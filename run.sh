#!/bin/sh
# 꽃피다(Bloomy) 실행 스크립트
set -e
cd "$(dirname "$0")"

if [ "$1" = "test" ]; then
  exec python3 scripts/smoke_test.py
fi

exec python3 backend/main.py "$@"
 