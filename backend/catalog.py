"""콘텐츠 큐레이션 — 카탈로그 (01 §7).

- Source of truth: `contents` 테이블(DB). `catalog/*.json` 파일들은 **seed
  파일**(4인 분담 구축: 60개, 나이별 15+). 로드 시 DB에 멱등 업서트.
- 레벨 (v1은 L1~L5, L6는 2차 확장) — 7.1:
    L1 노출·듣기 → L2 소리 인지 → L3 파닉스 → L4 사이트워드·초기 해독
    → L5 리더스 독해

항목 필드 8종 (7.1) — canonical 포맷:
  id, title, age_min, age_max, level("L1".."L5" 또는 1~5),
  skill(listening|speaking|reading|writing),
  type(readers_series|phonics|worksheet|video|audio|activity),
  provider(purchase 교재·부모 구입 | link 영상·오디오 공식 링크),
  link, session_minutes(10|15|20), expert_note, trust_source
레거시 포맷(stage/minutes/why/tip/paid)은 자동 매핑된다.
"""
import datetime as dt
import glob
import json
import os

import store

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
CATALOG_DIR = os.path.join(ROOT, "catalog")
# 레거시(구 명세) seed 파일 위치 — canonical catalog/로 이관 전 호환
_LEGACY_DATA = os.path.join(HERE, "data", "catalog.json")

LEVELS = {
    1: ("L1", "노출·듣기", "노래·동요·영상으로 영어의 리듬과 소리에 익숙해지는 단계"),
    2: ("L2", "소리 인지", "글자와 소리의 대응을 듣고 구분하기 시작하는 단계"),
    3: ("L3", "파닉스", "소리 조합(블렌딩)으로 짧은 단어를 읽기 시작하는 단계"),
    4: ("L4", "사이트워드·초기 해독", "자주 쓰는 단어를 보자마자 읽고 쉬운 책을 읽는 단계"),
    5: ("L5", "리더스 독해", "레벨드 리더스를 읽고 내용으로 짧게 이야기하는 단계"),
}

SKILLS = ("listening", "speaking", "reading", "writing")
TYPES = ("readers_series", "phonics", "worksheet", "video", "audio", "activity")

# 카드 작업·확인 포인트 템플릿 (canonical type + 레거시 한국어 type)
CARD_TEMPLATES = {
    "audio": ("'%s'을(를) 아이와 함께 듣기", "끝까지 들었나요? 따라 말하거나 반응(가리키기·모방)이 있었나요?"),
    "video": ("'%s'을(를) 아이와 함께 보기", "끝까지 봤나요? 그림을 가리키며 반응했나요?"),
    "readers_series": ("'%s'을(를) 아이와 함께 읽기 (오디오 있으면 듣고 따라하기)", "그림을 가리키며 뜻에 맞게 반응하나요?"),
    "phonics": ("'%s' 소리 하나씩 아이와 함께 연습하기", "글자 소리를 말할 수 있나요?"),
    "worksheet": ("'%s' 워크시트 함께 완료하기", "힌트 없이 대부분 해냈나요?"),
    "activity": ("'%s' 활동 함께 하기", "재밌어했나요? 다시 하고 싶어 했나요?"),
    # --- 레거시 타입 매핑 ---
    "노래": ("'%s' 노래를 듣고 따라 불러보기", "따라 부르거나 리듬에 반응했나요?"),
    "그림책": ("'%s' 그림책을 함께 읽기", "그림을 가리키며 뜻에 맞게 반응하나요?"),
    "영상": ("'%s' 영상을 함께 보기", "끝까지 봤나요? 그림을 가리키며 반응했나요?"),
    "워크시트": ("'%s' 워크시트 함께 완료하기", "힌트 없이 대부분 해냈나요?"),
    "활동": ("'%s' 활동 함께 하기", "재밌어했나요? 다시 하고 싶어 했나요?"),
    "읽기": ("'%s'을(를) 아이와 함께 읽기", "글자 소리를 내며 읽었나요?"),
    "유튜브": ("'%s' 영상을 함께 보기", "끝까지 봤나요? 그림을 가리키며 반응했나요?"),
    "교재": ("'%s' 교재와 함께 1회분 연습하기", "힌트 없이 대부분 해냈나요?"),
    "앱": ("'%s' 앱으로 함께 놀기", "재밌어했나요? 다시 하고 싶어 했나요?"),
    "웹": ("'%s' 웹 콘텐츠와 함께 하기", "끝까지 함께 했나요? 반응을 보여줬나요?"),
}
_DEFAULT_CARD = ("'%s'을(를) 아이와 함께 하기", "재밌어했나요? 다시 하고 싶어 했나요?")

_ITEMS = []


# ---------------------------------------------------------------------------
# seed / 로드
# ---------------------------------------------------------------------------

def _iter_files():
    files = sorted(glob.glob(os.path.join(CATALOG_DIR, "*.json")))
    if os.path.isfile(_LEGACY_DATA):
        files.append(_LEGACY_DATA)
    return files


def _iter_items():
    for fp in _iter_files():
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError("%s: 리스트(또는 {items: [...]})가 아닙니다" % fp)
        for it in items:
            yield fp, it


def _level_of(v):
    """'L3' | 3 | '3' → 3"""
    if isinstance(v, str) and v.strip().upper().startswith("L"):
        return int(v.strip()[1:])
    return int(v)


def normalize(item, source=""):
    """canonical 필드로 정규화. 필수 필드 누락이면 ValueError."""
    if not item.get("id") or not item.get("title"):
        raise ValueError("id/title 필수: %s (출처 %s)" % (item, source))
    legacy = "stage" in item
    try:
        level = _level_of(item.get("level", item.get("stage")))
    except (TypeError, ValueError):
        raise ValueError("%s: level(또는 stage)이 1~5 여야 합니다" % item.get("id"))
    if not (1 <= level <= 5):
        raise ValueError("%s: level 1~5 범위 (L6는 2차 확장)" % item.get("id"))
    age_min = int(item.get("age_min", 4))
    age_max = int(item.get("age_max", 7))
    if legacy:
        # 구 명세(3~6세) seed: 서비스 최소 연령이 4세이므로 4~7로 클램핑
        age_min = max(4, min(7, age_min))
        age_max = max(age_min, min(7, age_max))
    if not (4 <= age_min <= age_max <= 7):
        raise ValueError("%s: 나이 범위는 4~7세여야 합니다 (age_min=%s age_max=%s)"
                         % (item.get("id"), age_min, age_max))
    provider = item.get("provider") or ("purchase" if item.get("paid") else "link")
    if provider not in ("purchase", "link"):
        provider = "link"
    expert = (item.get("expert_note") or item.get("why") or "").strip()
    tip = (item.get("tip") or "").strip()
    if tip and expert and tip not in expert:
        expert = expert + " | 부모 팁: " + tip
    return {
        "id": str(item["id"]),
        "title": str(item["title"]),
        "age_min": age_min,
        "age_max": age_max,
        "level": level,
        "skill": str(item.get("skill") or ""),
        "type": str(item.get("type") or "activity"),
        "provider": provider,
        "link": str(item.get("link") or ""),
        "session_minutes": int(item.get("session_minutes") or item.get("minutes") or 10),
        "expert_note": expert,
        "trust_source": str(item.get("trust_source") or ""),
    }


_UPSERT = (
    "INSERT INTO contents(id, title, age_min, age_max, level, skill, type, provider, "
    "link, session_minutes, expert_note, trust_source) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET "
    "title=excluded.title, age_min=excluded.age_min, age_max=excluded.age_max, "
    "level=excluded.level, skill=excluded.skill, type=excluded.type, "
    "provider=excluded.provider, link=excluded.link, "
    "session_minutes=excluded.session_minutes, "
    "expert_note=excluded.expert_note, trust_source=excluded.trust_source"
)


def upsert_item(row):
    store.execute(
        _UPSERT,
        (row["id"], row["title"], row["age_min"], row["age_max"], row["level"],
         row["skill"], row["type"], row["provider"], row["link"],
         row["session_minutes"], row["expert_note"], row["trust_source"]),
    )


def load(strict=False):
    """JSON seed → DB 업서트(멱등) + 전체 메모리 로드.

    strict=True면 잘못된 항목이 하나라도 있으면 실패 (seed 스크립트용).
    기본(False)은 잘못된 항목만 스킵하고 경고 출력 (운영 안정성).
    """
    store.init()
    errors = []
    for fp, raw in _iter_items():
        try:
            upsert_item(normalize(raw, fp))
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    if errors and strict:
        raise ValueError("카탈로그 검증 실패:\n" + "\n".join(errors))
    if errors:
        print("[bloomy-catalog] %d개 항목 스킵:\n%s" % (len(errors), "\n".join(errors)))
    global _ITEMS
    _ITEMS = store.query(
        "SELECT * FROM contents ORDER BY level, age_min, id"
    )
    return len(_ITEMS), errors


def validate():
    """seed 스크립트용: (items, errors) 반환 — DB 쓰지 않음."""
    items, errors = [], []
    seen = set()
    for fp, raw in _iter_items():
        try:
            row = normalize(raw, fp)
            if row["id"] in seen:
                errors.append("중복 id: %s" % row["id"])
            seen.add(row["id"])
            items.append(row)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return items, errors


def stats(items=None):
    """게이트 G3 점검용: 총개수·나이별 15+·레벨 분포."""
    items = items if items is not None else _ITEMS
    by_age = {4: 0, 5: 0, 6: 0, 7: 0}
    by_level = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for it in items:
        for age in range(4, 8):
            if it["age_min"] <= age <= it["age_max"]:
                by_age[age] += 1
        by_level[it["level"]] = by_level.get(it["level"], 0) + 1
    return {
        "total": len(items),
        "by_age": by_age,
        "by_level": by_level,
        "gate_ok": len(items) >= 45 and all(v >= 15 for v in by_age.values()),
    }


# ---------------------------------------------------------------------------
# 검색
# ---------------------------------------------------------------------------

def find_item(item_id):
    if not item_id:
        return None
    for it in _ITEMS:
        if it["id"] == item_id:
            return it
    return None


def items_by_level(level, age=None):
    out = []
    for it in _ITEMS:
        if it["level"] != level:
            continue
        if age is not None and not (it["age_min"] <= age <= it["age_max"]):
            continue
        out.append(it)
    return out


def search(age=None, level=None, skill=None, type_=None, keyword=None):
    out = []
    kw = (keyword or "").lower()
    for it in _ITEMS:
        if age is not None and not (it["age_min"] <= age <= it["age_max"]):
            continue
        if level is not None and it["level"] != level:
            continue
        if skill is not None and it.get("skill") and it["skill"] != skill:
            continue
        if type_ is not None and it["type"] != type_:
            continue
        if kw and kw not in (it["title"] + " " + it.get("expert_note", "")).lower():
            continue
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# 규칙 기반 계획 생성 (온보딩·replan 기본 — A의 RAG 추천과 같은 cards 형식)
# ---------------------------------------------------------------------------

def next_weekdays(start, n):
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:  # 평일(월~금)만 학습일
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def card_text(item):
    t, c = CARD_TEMPLATES.get(
        item.get("type", ""), _DEFAULT_CARD
    )
    # 일부 템플릿(체크 포인트)에는 %s 플레이스홀더가 없다
    if "%s" in t:
        t = t % item["title"]
    if "%s" in c:
        c = c % item["title"]
    return t, c


def plan_explanation(child, base):
    code, name, desc = LEVELS[base]
    return (
        "시작 단계는 %s (%s) — %s\n\n"
        "왜 이 순서인지: 먼저 소리와 리듬에 익숙해지고, 글자-소리 대응, 읽기, "
        "그리고 말하기 순서로 나아가는 게 '영어로 생각하는' 힘이 자연스럽게 쌓이는 "
        "순서예요. 수요일은 %s 워밍업으로 리듬을 살리고, 금요일은 한 단계 위를 살짝 "
        "도전해요.\n\n"
        "부모 보조 팁: 하루 %d분, 옆에 앉아 아이가 가리키거나 따라 하는 것만 봐주세요. "
        "영어를 잘해야 하는 게 아닙니다. "
        "이 계획은 가정(hypothesis)이라 2주 반응 데이터로 조정돼요."
        % (code, name, desc, LEVELS[1][0], child.get("session_length") or 10)
    )


def generate_plan(child, start):
    """4주(20 학습일) 계획 초안 (규칙 기반 기본 생성기).

    A의 커리큘럼 추천(RAG, 6.2)이 같은 cards 형식으로 이 결과를 대체/보완한다.
    주간 패턴 (실제 캘린더 요일 기준 — 시작일 요일에 무관하게 일정한 리듬):
        월/화/목: 주(base) 레벨
        수:       L1 워밍업
        금:       주 레벨 + 1 (한 단계 위 살짝 도전)
    학습일 11일째부터(3주차 블록) 주 레벨이 한 단계 올라간다.
    """
    base = max(1, min(5, int(child.get("level") or 2)))
    dates = next_weekdays(start, 20)
    used = {}
    cards = []
    for i, d in enumerate(dates):
        week = i // 5
        main_level = base if week < 2 else min(5, base + 1)
        if d.weekday() == 2:  # 수요일: L1 워밍업
            level = 1
        elif d.weekday() == 4:  # 금요일: 한 단계 위 도전
            level = min(5, main_level + 1)
        else:  # 월/화/목
            level = main_level
        pool = (
            items_by_level(level, child["age"])
            or items_by_level(level)
            or list(_ITEMS)
        )
        item = pool[used.get(level, 0) % len(pool)] if pool else None
        used[level] = used.get(level, 0) + 1
        if item is None:
            cards.append({
                "date": d.isoformat(), "content_id": None,
                "task": "카탈로그 항목이 준비되는 중이에요. 오늘은 5분 영어 노래 시간!",
                "minutes": min(5, child.get("session_length") or 10),
                "check_point": "아이가 영어 소리에 반응했나요?",
            })
            continue
        task, check = card_text(item)
        cards.append({
            "date": d.isoformat(),
            "content_id": item["id"],
            "task": task,
            "minutes": min(int(item.get("session_minutes") or 10),
                           int(child.get("session_length") or 10)),
            "check_point": check,
        })
    return {
        "base_level": base,
        "explanation": plan_explanation(child, base),
        "cards": cards,
    }
