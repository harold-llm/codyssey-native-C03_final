"""보유 교재 입력을 카탈로그 항목과 연결한다.

부모는 'ORT', '옥스포드', '핑크퐁'처럼 약어·한글 표기로 적는다. 제목 부분 일치만으로는
이를 알아보지 못하므로(예: 'ORT'는 'Oxford Reading Tree'에 포함되지 않음)
별칭 표와 ID 접두어(ort → ort-stage1 …)로 함께 판정한다.
"""
import re

# 별칭(소문자, 공백 제거 기준) → 카탈로그 제목에 들어 있는 정식 표기(소문자)
ALIASES = {
    "ort": "oxford reading tree", "옥스포드": "oxford reading tree", "옥스퍼드": "oxford reading tree",
    "오알티": "oxford reading tree", "옥스포드리딩트리": "oxford reading tree", "옥스퍼드리딩트리": "oxford reading tree",
    "핑크퐁": "pinkfong", "아기상어": "pinkfong",
    "슈퍼심플": "super simple songs", "슈퍼심플송": "super simple songs", "sss": "super simple songs",
    "에릭칼": "eric carle", "에릭카를": "eric carle",
    "어스본": "usborne", "어스본리더스": "usborne",
    "졸리파닉스": "jolly phonics", "졸리": "jolly phonics",
    "밥북스": "bob books", "밥북": "bob books",
    "닥터수스": "dr. seuss", "닥터세우스": "dr. seuss",
    "피트더캣": "pete the cat",
    "코코멜론": "cocomelon",
    "페파피그": "peppa pig", "페파": "peppa pig",
    "알파블럭스": "alphablocks", "알파블록스": "alphablocks",
    "립프로그": "leapfrog",
    "스콜라스틱": "scholastic",
    "리딩에그": "reading eggs", "리딩에그스": "reading eggs",
    "라즈키즈": "raz-kids", "raz": "raz-kids", "razkids": "raz-kids",
    "에픽": "epic!",
    "칸아카데미": "khan academy", "칸키즈": "khan academy",
    "스타폴": "starfall",
    "에이비씨마우스": "abcmouse",
    "매직스쿨버스": "the magic school bus",
    "내셔널지오그래픽": "national geographic", "내셔널지오": "national geographic", "natgeo": "national geographic",
    "엘리펀트앤피기": "elephant & piggie", "코끼리와꿀꿀이": "elephant & piggie",
    "플라이가이": "fly guy",
    "매직트리하우스": "magic tree house", "mth": "magic tree house",
    "네이트더그레이트": "nate the great",
    "주니비존스": "junie b. jones",
    "개구리와두꺼비": "frog and toad", "프로그앤토드": "frog and toad",
    "아멜리아베델리아": "amelia bedelia",
}


def _compact(text):
    return re.sub(r"[\s\-_.,·'!&]+", "", text.casefold())


def _canonicals(term):
    """입력 한 항목이 가리키는 정식 표기 목록."""
    lowered = term.casefold()
    compact = _compact(term)
    found = []
    for alias, canonical in ALIASES.items():
        if alias.isascii():
            # 영문 약어는 단어 경계로만 (예: 'ort'가 'short' 안에서 맞지 않도록)
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
                found.append(canonical)
        elif alias in compact:
            found.append(canonical)
    return found


def is_owned(item, terms):
    """카탈로그 항목이 부모가 적은 보유 교재 중 하나에 해당하는지."""
    title = item["title"].casefold()
    title_compact = _compact(item["title"])
    item_id = item["id"].casefold()
    for raw in terms:
        term = raw.strip()
        if not term:
            continue
        compact = _compact(term)
        lowered = term.casefold()
        # 카탈로그 ID 그대로(demo-speaking-001) 또는 시리즈 접두어(ort → ort-stage1)
        if lowered == item_id or item_id.startswith(lowered + "-") or item_id.startswith(compact + "-"):
            return True
        if lowered in title:
            return True
        if len(compact) >= 4 and (compact in title_compact or title_compact in compact):
            return True
        if any(canonical in title for canonical in _canonicals(term)):
            return True
    return False
