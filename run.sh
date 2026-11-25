#!/bin/sh
# 꽃피다(Bloomy) 실행 스크립트
set -e
cd "$(dirname "$0")"

if [ "$1" = "test" ]; then
  exec python3 scripts/smoke_test.py
fi

# .env(깃에 올라가지 않음)가 있으면 읽는다. 예: ANTHROPIC_API_KEY=... → Vercel과 같은 Claude 모드
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

exec python3 backend/main.py "$@"
