"""서비스 기준 시각 — 한국 시간(KST, UTC+9).

Vercel 서버는 UTC로 동작하므로 `date.today()`를 그대로 쓰면 한국 자정~오전 9시에
'오늘'이 하루 전으로 계산된다. 날짜·시각 계산은 모두 이 모듈을 거친다.
한국은 서머타임이 없어 고정 오프셋을 쓴다 (tzdata 의존 없음).
`BLOOMY_TZ_OFFSET_HOURS`로 바꿀 수 있다 (기본 9).
"""
from __future__ import annotations

import datetime as dt
import os


def _offset_hours() -> float:
    try:
        return float(os.environ.get("BLOOMY_TZ_OFFSET_HOURS", "9"))
    except ValueError:
        return 9.0


TZ = dt.timezone(dt.timedelta(hours=_offset_hours()))


def now() -> dt.datetime:
    """서비스 기준 현재 시각 (timezone-aware)."""
    return dt.datetime.now(TZ)


def today() -> dt.date:
    """서비스 기준 오늘 날짜."""
    return now().date()
