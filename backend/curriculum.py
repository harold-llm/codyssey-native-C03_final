"""학습 단위(권·에피소드) 커리큘럼 — 카드 문구를 '어떤 책의 무엇을 할지'로 바꾼다.

데이터: `data/content_guide.json`
  - series: 시리즈·서비스 설명 (문서 docs/catalog.md 생성용)
  - unit_packs: 학습 단위 묶음 (예: ORT Stage 2 팩 6종 36권, 공식 목록에서 확인한 제목만)
  - items: 카탈로그 항목별 찾는 법·단위 구성

같은 자료가 계획에 여러 번 나오면 1권 첫 읽기 → 1권 다시 읽기 → 2권 첫 읽기 …
순서로 진도가 나간다. 이전 계획에서 진행한 횟수부터 이어간다.
저작권(기획서 §7.3): 제목·팩 이름·활동 방법만 다루고 본문은 싣지 않는다.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, MutableMapping, Sequence
from typing import cast

import store

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE_PATH = os.path.join(HERE, "data", "content_guide.json")

_guide: dict[str, object] | None = None


def guide() -> dict[str, object]:
    global _guide
    if _guide is None:
        with open(GUIDE_PATH, encoding="utf-8") as f:
            _guide = cast("dict[str, object]", json.load(f))
    return _guide


def _section(name: str) -> dict[str, dict[str, object]]:
    return cast("dict[str, dict[str, object]]", guide().get(name) or {})


def units(content_id: str) -> list[dict[str, str]]:
    """항목의 학습 단위 목록 [{title, pack, template}] (없으면 빈 목록)."""
    entry = _section("items").get(content_id) or {}
    packs = _section("unit_packs")
    out: list[dict[str, str]] = []
    for key in cast("list[str]", entry.get("units") or []):
        group = packs.get(key) or {}
        template = str(group.get("template") or "")
        for pack, titles in cast("list[tuple[str, list[str]]]", group.get("packs") or []):
            out.extend({"title": t, "pack": pack, "template": template} for t in titles)
    return out


def unit_text(content_id: str | None, nth: int) -> tuple[str, str] | None:
    """해당 자료를 nth번째(0부터) 할 때의 (task, check_point). 단위가 없으면 None.

    한 권을 두 번(첫 읽기·다시 읽기) 하고 다음 권으로 넘어간다. 끝까지 가면 처음부터.
    """
    if not content_id:
        return None
    us = units(content_id)
    if not us:
        return None
    unit = us[(nth // 2) % len(us)]
    tpl = _section("unit_templates").get(unit["template"]) or {}
    mode = "first" if nth % 2 == 0 else "reread"
    task = str(tpl.get(mode) or "『{title}』({pack}) 읽기")
    check = str(tpl.get("check_" + mode) or "끝까지 함께 읽었나요?")
    return task.format(title=unit["title"], pack=unit["pack"]), check


def prior_counts(child_id: int) -> dict[str, int]:
    """이전 계획(승인·완료)에서 자료별로 몇 번 했는지 — 진도를 이어가기 위해."""
    rows = store.query(
        "SELECT c.content_id AS content_id, COUNT(*) AS n FROM cards c "
        "JOIN plans p ON p.id = c.plan_id "
        "WHERE c.child_id = ? AND p.status IN ('approved', 'done') "
        "AND c.content_id IS NOT NULL GROUP BY c.content_id",
        (child_id,),
    )
    return {str(r["content_id"]): int(cast("int", r["n"])) for r in rows}


def apply(
    cards: Sequence[MutableMapping[str, object]], start: Mapping[str, int] | None = None,
) -> None:
    """계획 카드의 task·check_point를 학습 단위 문구로 바꾼다 (단위가 있는 자료만, 제자리 수정)."""
    seen = dict(start or {})
    # 같은 책을 여러 항목이 공유한다 (예: songbirds-1 ⊂ songbirds-full) → 이미 배정한 회차는 건너뛴다
    assigned: set[tuple[str, int]] = set()
    for card in cards:
        cid = card.get("content_id")
        if not isinstance(cid, str):
            continue
        us = units(cid)
        if not us:
            continue
        n = seen.get(cid, 0)
        for _ in range(len(us) * 2):
            u = us[(n // 2) % len(us)]
            if (u["pack"] + "|" + u["title"], n % 2) not in assigned:
                break
            n += 1
        text = unit_text(cid, n)
        if text is None:
            continue
        u = us[(n // 2) % len(us)]
        assigned.add((u["pack"] + "|" + u["title"], n % 2))
        seen[cid] = n + 1
        card["task"], card["check_point"] = text
