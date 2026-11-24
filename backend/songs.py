"""오늘의 영어 동요 — 학습 단계(L1~L5)에 맞춰 날마다 공식 채널 YouTube 영상 1곡을 안내한다.

앱 안에서 재생하지 않는다. 부모에게 "무엇을, 어떻게 함께 들을지"와 공식 링크만 준다.
데이터: data/songs.json (링크는 scripts/check_songs.py로 공식 채널 여부를 확인)
"""
from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Mapping
from typing import cast

import catalog
import curriculum

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "songs.json")
_songs: list[dict[str, object]] | None = None

REVIEW_EVERY = 3  # 사흘에 한 번은 한 단계 아래 노래로 복습


def all_songs() -> list[dict[str, object]]:
    global _songs
    if _songs is None:
        with open(_PATH, encoding="utf-8") as f:
            _songs = cast("list[dict[str, object]]", json.load(f)["songs"])
    return _songs


def _level(child: Mapping[str, object], plan: Mapping[str, object] | None) -> int:
    raw = (plan or {}).get("base_level") or child.get("level") or 1
    try:
        return max(1, min(5, int(cast("int | str", raw))))
    except (TypeError, ValueError):
        return 1


def song_for(child: Mapping[str, object], date: str,
             plan: Mapping[str, object] | None = None) -> dict[str, object] | None:
    """그날의 동요 1곡. 같은 아이·같은 날짜면 항상 같은 곡, 날마다 다른 곡."""
    level = _level(child, plan)
    if curriculum.needs_alphabet(child):
        level = 2  # 알파벳을 모르는 아이는 알파벳·글자 소리 노래부터
    day = dt.date.fromisoformat(date).toordinal()
    review = level > 1 and day % REVIEW_EVERY == 0
    target = level - 1 if review else level
    pool = [s for s in all_songs() if s["level"] == target]
    if not pool:
        return None
    seed = int(cast("int | str", child.get("id") or 0)) * 7
    song = pool[(day + seed) % len(pool)]
    code, name, _desc = catalog.LEVELS[target]
    why = (f"{code} {name} 노래로 복습하는 날이에요." if review
           else f"지금 단계({code} {name})에 맞춘 노래예요.")
    return {**song, "level_label": f"{code} {name}", "why": why, "review": review}
