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
import re
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


# ---------------------------------------------------------------------------
# 카드 안내 — '무엇을, 어디서, 어떻게 도와줄지' (피드백 보고서 1·2·5)
# 이 서비스는 콘텐츠를 직접 제공하지 않는다. 외부 자료를 어떻게 쓸지 안내만 한다.
# ---------------------------------------------------------------------------

SKILL_KO = {"listening": "듣기", "speaking": "말하기", "reading": "읽기", "writing": "쓰기"}

# 주 목표(skill) 하나에 활동·확인 포인트를 맞춘다 (보고서 2: 활동과 확인 목표 불일치)
_GOAL_TASK = {
    ("listening", "video"): "{title} — 함께 보며 노래·동작을 따라 하기",
    ("listening", "audio"): "{title} — 함께 들으며 따라 부르기",
    ("listening", "readers_series"): "{title} — 부모가 읽어 주고 아이는 그림을 가리키며 듣기",
    ("listening", "activity"): "{title} — 소리 듣기 활동을 함께 하고 들은 단어 따라 말하기",
    ("speaking", "activity"): "{title} — 카드를 보여 주며 짧게 영어로 말하고 몸으로 표현하기",
    ("reading", "readers_series"): "{title} — 함께 읽으며 글자를 손가락으로 짚기",
    ("reading", "phonics"): "{title} — 글자 소리를 하나씩 내고 합쳐 보기",
    ("reading", "activity"): "{title} — 읽기 활동 1회를 함께 하고 나온 단어 하나 다시 읽기",
    ("reading", "video"): "{title} — 함께 보며 화면 속 글자와 소리를 짝지어 따라 말하기",
    ("writing", "worksheet"): "{title} — 소리를 말하며 글자를 따라 쓰기",
}
_GOAL_CHECK = {
    "listening": "소리나 몸짓(따라 부르기·가리키기)으로 반응했나요?",
    "speaking": "단어나 짧은 표현을 소리 내어 말했나요?",
    "reading": "글자를 보고 소리나 단어를 말했나요?",
    "writing": "소리를 말하며 글자를 써 봤나요?",
}

# 부모가 옆에서 할 일 (자료 유형별)
_HELP = {
    "video": "공식 링크로 열어 옆에서 같이 봐요. 노래·동작이 나오면 부모가 먼저 크게 따라 해 주세요. 끝까지 봤다고 '익혔다'로 보지 않고, 반응만 기록해요.",
    "audio": "음원을 틀고 같이 따라 불러요. 가사를 몰라도 리듬에 맞춰 손뼉만 쳐도 충분해요.",
    "readers_series": "부모가 손가락으로 글자를 짚으며 읽어 주고, 반복되는 문장은 아이에게 넘겨요. 틀려도 고치지 말고 다시 읽어 주기만 해요.",
    "phonics": "부모가 소리를 먼저 또박또박 내 주고 아이가 따라 하게 해요. 글자 이름(에이)이 아니라 소리(애)로 말해요.",
    "worksheet": "한 번에 2~3쪽만 해요. 아이가 소리를 말하며 쓰게 하고, 모양이 서툴러도 괜찮아요.",
    "activity": "앱·카드는 부모가 열고 정해진 시간만 옆에서 함께 해요. 끝나면 오늘 나온 단어 하나를 같이 말해 봐요.",
}


def goal_text(title: str, skill: str, type_: str) -> tuple[str, str]:
    """주 목표 하나에 맞춘 (활동, 확인 포인트)."""
    task = _GOAL_TASK.get((skill, type_)) or "{title} — 함께 하며 " + SKILL_KO.get(skill, "") + " 연습하기"
    return task.format(title=title), _GOAL_CHECK.get(skill, "끝까지 함께 했나요?")


def granularity(content_id: str | None) -> str:
    entry = _section("items").get(content_id or "") or {}
    return str(entry.get("granularity") or "collection")


def collection_ids() -> set[str]:
    return {k for k, v in _section("items").items() if v.get("granularity") == "collection"}


def card_info(item: Mapping[str, object] | None, child: Mapping[str, object] | None = None,
              owned: bool = False) -> dict[str, object] | None:
    """카드에 붙일 자료 안내: 무엇인지·어디서·비용·왜·부모 역할."""
    if not item:
        return None
    cid = str(item.get("id") or "")
    entry = _section("items").get(cid) or {}
    series = _section("series").get(str(entry.get("series") or "")) or {}
    level = int(cast("int", item.get("level") or 1))
    level_name = {1: "노출·듣기", 2: "소리 인지", 3: "파닉스", 4: "사이트워드·초기 해독", 5: "리더스 독해"}.get(level, "")
    skill = str(item.get("skill") or "")
    why = [f"L{level} {level_name} 단계, {item.get('age_min')}~{item.get('age_max')}세 대상 {SKILL_KO.get(skill, '')} 자료예요."]
    if owned:
        why.append("집에 있다고 알려 주신 교재라 먼저 골랐어요.")
    if granularity(cid) == "units":
        why.append("권·회차 순서가 정해진 자료라 매일 이어서 진도를 나가요.")
    return {
        "title": item.get("title"),
        "kind": series.get("kind"),
        "about": series.get("about"),
        "find": entry.get("find"),
        "link": item.get("link"),
        "cost": series.get("cost"),
        "why": " ".join(why),
        "help": _HELP.get(str(item.get("type") or ""), _HELP["activity"]),
        "specific": granularity(cid) != "collection",
    }


_COMPLETION_KO = {"full": "끝까지 함", "partial": "일부 함", "none": "못 함"}


def basis(child: Mapping[str, object], card: Mapping[str, object] | None) -> str | None:
    """이 카드가 아이의 어떤 기록을 근거로 정해졌는지 (보고서 5). 기록이 없으면 None — 지어내지 않는다."""
    if not card:
        return None
    cid = int(cast("int", child["id"]))
    prev = store.last_feedback_before(cid, str(card["date"]))
    if not prev or prev.get("rest_day"):
        return None
    parts = [f"지난 기록({prev['date']}): {_COMPLETION_KO.get(str(prev.get('completion')), '')}"
             f" · 흥미 {prev.get('interest')} · 이해도 {prev.get('comprehension')}"]
    session = int(cast("int", child.get("session_length") or 10))
    minutes = int(cast("int", card.get("minutes") or session))
    if minutes < session:
        parts.append(f"→ 부담을 줄이려고 오늘 분량을 {minutes}분으로 줄였어요 (설정 {session}분).")
    elif (prev_card := store.get_card_for_child(cid, str(prev["date"]))) and \
            prev_card.get("content_id") and prev_card.get("content_id") == card.get("content_id"):
        parts.append("→ 같은 자료를 이어서 해요. 반복이 익숙함을 만들어요.")
    elif int(cast("int", prev.get("interest") or 0)) <= 2:
        parts.append("→ 흥미가 낮았던 다음 날이라 부담 없이 짧게 해 보세요.")
    else:
        parts.append("→ 계획대로 이어서 진행해요.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 알파벳을 아직 모르는 아이 (보호자 피드백: "ABC부터 나왔으면")
# 앱이 알파벳을 가르치는 게 아니라, 계획에서 외부 알파벳 자료를 먼저 배치한다.
# ---------------------------------------------------------------------------

# 외부 알파벳 자료 (순환 순서). Jolly Phonics는 학습 단위(소리 그룹)로 진도가 나간다.
ALPHABET_ROTATION = ("sss-abc", "jolly-songs", "starfall-abcs", "jolly-full", "jolly-letter", "leapfrog-letter")
_NAME_ALPHABET_IDS = ("sss-abc", "starfall-abcs", "leapfrog-letter")  # 글자 이름(A, B, C) 중심 자료

# 글자(소리) → 그림 단어. 4~7세가 그림으로 알 수 있는 단어만.
LETTER_WORDS: dict[str, tuple[str, str]] = {
    "a": ("apple", "🍎"), "b": ("ball", "⚽"), "c": ("cat", "🐱"), "d": ("dog", "🐶"), "e": ("egg", "🥚"),
    "f": ("fish", "🐟"), "g": ("goat", "🐐"), "h": ("hat", "🎩"), "i": ("insect", "🐞"), "j": ("jam", "🍓"),
    "k": ("kite", "🪁"), "l": ("lion", "🦁"), "m": ("moon", "🌙"), "n": ("nest", "🪺"), "o": ("octopus", "🐙"),
    "p": ("pig", "🐷"), "q": ("queen", "👑"), "r": ("rabbit", "🐰"), "s": ("sun", "☀️"), "t": ("tiger", "🐯"),
    "u": ("umbrella", "☂️"), "v": ("van", "🚐"), "w": ("whale", "🐳"), "x": ("box", "📦"), "y": ("yo-yo", "🪀"),
    "z": ("zebra", "🦓"),
    "ai": ("rain", "🌧️"), "oa": ("boat", "⛵"), "ie": ("tie", "👔"), "ee": ("tree", "🌳"), "or": ("fork", "🍴"),
    "ng": ("ring", "💍"), "ch": ("chick", "🐥"), "sh": ("ship", "🚢"), "th": ("thumb", "👍"), "qu": ("queen", "👑"),
    "ou": ("cloud", "☁️"), "oi": ("coin", "🪙"), "ue": ("glue", "🧴"), "er": ("flower", "🌸"), "ar": ("car", "🚗"),
    "oo": ("moon", "🌙"),
}


def needs_alphabet(child: Mapping[str, object]) -> bool:
    """진단에서 알파벳 '인지 못 함'인지."""
    raw = child.get("diagnosis")
    try:
        diag = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return False
    answers = cast("dict[str, object]", cast("dict[str, object]", diag).get("answers") or {})
    return answers.get("alphabet") == "none"


def alphabet_first(child: Mapping[str, object], cards: Sequence[MutableMapping[str, object]],
                   find_item, card_text) -> bool:
    """알파벳을 모르는 아이: 첫 주(5일)는 알파벳 자료, 이후에는 이틀에 한 번 알파벳 자료.

    find_item·card_text는 catalog 모듈 함수 (순환 import 방지). 바꿨으면 True.
    """
    if not needs_alphabet(child) or not cards:
        return False
    age = int(cast("int", child.get("age") or 4))
    session = int(cast("int", child.get("session_length") or 10))
    pool = [it for it in (find_item(i) for i in ALPHABET_ROTATION)
            if it and it["age_min"] <= age <= it["age_max"]]
    if not pool:
        return False
    k = 0
    for i, card in enumerate(cards):
        if i < 5 or i % 2 == 0:
            item = pool[k % len(pool)]
            k += 1
            card["content_id"] = item["id"]
            card["task"], card["check_point"] = card_text(item)
            card["minutes"] = min(int(item["session_minutes"]), session)
    return True


def letters_for(child: Mapping[str, object], card: Mapping[str, object] | None) -> list[dict[str, str]]:
    """알파벳 자료 카드에 '오늘의 글자'를 붙인다. 그 외 카드는 빈 목록."""
    if not card:
        return []
    cid = str(card.get("content_id") or "")
    out: list[dict[str, str]] = []
    if cid.startswith("jolly-"):
        m = re.search(r"소리(?: 복습)? (.+?) \(Group", str(card.get("task") or ""))
        if not m:
            return []
        for tok in m.group(1).split(" · "):
            for sound in re.sub(r"\(.*?\)", "", tok).split():
                if sound in LETTER_WORDS:
                    word, emoji = LETTER_WORDS[sound]
                    out.append({"letter": sound, "word": word, "emoji": emoji, "say": word})
        return out
    if cid in _NAME_ALPHABET_IDS:
        rows = store.query(
            "SELECT COUNT(*) AS n FROM cards c JOIN plans p ON p.id = c.plan_id "
            "WHERE c.child_id = ? AND c.content_id = ? AND c.date < ? "
            "AND p.status IN ('approved', 'done')",
            (int(cast("int", child["id"])), cid, str(card.get("date") or "")),
        )
        nth = int(cast("int", rows[0]["n"])) if rows else 0
        start = (nth * 3) % 26
        for off in range(3):
            ch = "abcdefghijklmnopqrstuvwxyz"[(start + off) % 26]
            word, emoji = LETTER_WORDS[ch]
            out.append({"letter": f"{ch.upper()} {ch}", "word": word, "emoji": emoji, "say": f"{ch.upper()}. {word}"})
    return out
