"""RAG 추천 자료 문서 생성기 → 05-RAG-추천-자료.md

원본: backend/data/catalog.json (RAG·규칙 계획이 실제로 쓰는 항목)
     backend/data/content_guide.json (시리즈 설명·찾는 법·학습 단위)
     backend/data/songs.json (오늘의 동요, 단계별 YouTube 공식 채널 영상)

실행:
  python3 scripts/gen_catalog_doc.py          # 문서 다시 쓰기
  python3 scripts/gen_catalog_doc.py --check  # 문서가 최신인지 검사 (다르면 exit 1)

자동 갱신: .githooks/pre-commit 이 위 JSON이 바뀐 커밋마다 실행하고,
smoke test가 --check로 오래된 문서를 잡는다.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backend", "data")
DOC_NAME = "05-RAG-추천-자료.md"
OUT = os.path.join(ROOT, DOC_NAME)
sys.path.insert(0, os.path.join(ROOT, "backend"))

LEVELS = {
    1: ("L1", "노출·듣기"), 2: ("L2", "소리 인지"), 3: ("L3", "파닉스"),
    4: ("L4", "사이트워드·초기 해독"), 5: ("L5", "리더스 독해"),
}
TYPES = {"readers_series": "리더스·그림책", "phonics": "파닉스", "worksheet": "워크시트",
         "video": "영상", "audio": "오디오", "activity": "앱·활동"}
SKILLS = {"listening": "듣기", "speaking": "말하기", "reading": "읽기", "writing": "쓰기"}
GRAN_MARK = {"title": "단일 작품", "units": "학습 단위", "collection": "묶음"}


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def render() -> str:
    import curriculum  # unit 전개 로직을 문서와 서비스가 공유

    catalog = _load("catalog.json")
    g = _load("content_guide.json")
    series, items = g["series"], g["items"]
    missing = [it["id"] for it in catalog if it["id"] not in items]
    if missing:
        raise SystemExit("content_guide.json에 안내가 없는 카탈로그 항목: " + ", ".join(missing))

    gran = Counter(items[it["id"]]["granularity"] for it in catalog)
    by_series = defaultdict(list)
    for it in catalog:
        by_series[items[it["id"]]["series"]].append(it)
    n_units = len({(u["pack"], u["title"]) for it in catalog for u in curriculum.units(it["id"])})

    L = []
    w = L.append
    w("# 05. RAG 추천 자료 목록 — 꽃피다 (Bloomy)")
    w("")
    w("> **자동 생성 문서입니다. 직접 고치지 마세요.** 원본은 `backend/data/catalog.json`(추천 대상 항목)과")
    w("> `backend/data/content_guide.json`(설명·찾는 법·학습 단위)이며, `python3 scripts/gen_catalog_doc.py`로 다시 만듭니다.")
    w("> 두 파일을 바꾼 커밋은 pre-commit 훅이 이 문서를 자동으로 갱신합니다.")
    w("")
    w("## 한눈에 보기")
    w("")
    w("- 꽃피다는 콘텐츠를 직접 제공하지 않습니다. 부모가 이미 갖고 있거나 쉽게 구할 수 있는 **외부 자료**(책·앱·영상) 중")
    w("  **무엇을, 어느 부분을, 어떻게** 할지 매일 카드로 알려 줍니다. 아래 목록이 그 추천 후보 전체입니다.")
    w("- 온보딩 4주 계획은 이 카탈로그에서 RAG 검색(나이·레벨·하루 시간·보유 교재 필터 + TF-IDF(Term Frequency 단어 빈도 · Inverse Document Frequency 역문서 빈도))으로 후보를 찾고,")
    w("  Claude가 후보 ID 안에서만 20일 순서를 정합니다. 후보 밖의 자료는 추천할 수 없습니다.")
    w(f"- 항목 **{len(catalog)}개**, 시리즈·서비스 **{len(by_series)}종**, 출처를 확인한 학습 단위 **{n_units}개** (책 한 권 또는 소리 묶음 하나)")
    w("")
    w("| 구체성 | 항목 수 | 뜻 |")
    w("|---|---|---|")
    for key in ("units", "title", "collection"):
        w(f"| {GRAN_MARK[key]} | {gran.get(key, 0)} | {g['granularity_labels'][key]} |")
    w("")
    w("레벨: " + " → ".join(f"{c} {n}" for c, n in LEVELS.values()))
    w("")

    w(f"## 전체 목록 ({len(catalog)}개)")
    w("")
    w("RAG가 검색하는 대상 전체입니다. 레벨·나이 순. 자료별 설명·찾는 법·학습 단위는 아래 '시리즈·서비스별 안내'에 있습니다.")
    w("")
    w("| # | 자료 | 시리즈·서비스 | 유형 | 나이 | 레벨 | 하루 | 구체성 | 항목 ID |")
    w("|---|---|---|---|---|---|---|---|---|")
    for n, it in enumerate(sorted(catalog, key=lambda x: (x["level"], x["age_min"], x["age_max"], x["title"])), 1):
        info = items[it["id"]]
        code, _ = LEVELS[it["level"]]
        w(f"| {n} | {it['title']} | {series[info['series']]['name']} | {TYPES.get(it['type'], it['type'])} | "
          f"{it['age_min']}~{it['age_max']}세 | {code} | {it['session_minutes']}분 | {GRAN_MARK[info['granularity']]} | `{it['id']}` |")
    w("")

    w("## 시리즈·서비스별 안내")
    w("")
    w("처음 보는 자료라면 여기서 '이게 무엇인지'부터 확인하세요.")
    w("")
    order = sorted(by_series, key=lambda s: (min(i["level"] for i in by_series[s]), series[s]["name"]))
    for s in order:
        info = series[s]
        its = by_series[s]
        w(f"### {info['name']}")
        w("")
        link = f" · [공식 사이트]({info['official']})" if info.get("official") else ""
        cost = f" · 비용: {info['cost']}" if info.get("cost") else ""
        w(f"*{info['kind']}*{cost}{link}")
        w("")
        w(info["about"])
        w("")
        path = info.get("path")
        if path:
            w(f"**공식 단계 전체** — {path.get('note', '')} ([출처]({path['source']}))")
            w("")
            for n, st in enumerate(path.get("steps") or [], 1):
                age = f" · {st['age']}" if st.get("age") else ""
                desc = f" — {st['desc']}" if st.get("desc") else ""
                mark = f" ← 꽃피다 추천: {', '.join(f'`{i}`' for i in st['items'])}" if st.get("items") else ""
                w(f"{n}. {st['name']}{age}{desc}{mark}")
            w("")
        w("| 항목 ID | 카탈로그 제목 | 나이 | 레벨 | 유형 | 하루 | 구체성 | 어디서 무엇을 찾나 |")
        w("|---|---|---|---|---|---|---|---|")
        for it in sorted(its, key=lambda i: (i["level"], i["id"])):
            e = items[it["id"]]
            w(f"| `{it['id']}` | {it['title']} | {it['age_min']}~{it['age_max']}세 | {LEVELS[it['level']][0]} | "
              f"{TYPES.get(it['type'], it['type'])}·{SKILLS.get(it['skill'], it['skill'])} | {it['session_minutes']}분 | "
              f"{GRAN_MARK[e['granularity']]} | {e['find']} |")
        w("")
        for it in its:
            us = curriculum.units(it["id"])
            if not us:
                continue
            w(f"<details><summary><code>{it['id']}</code> 학습 단위 {len(us)}개 (진행 순서)</summary>")
            w("")
            pack = None
            for i, u in enumerate(us, 1):
                if u["pack"] != pack:
                    pack = u["pack"]
                    w(f"- **{pack}**")
                w(f"  {i}. {u['title']}")
            w("")
            w("</details>")
            w("")

    w("## 학습 단위 카드는 이렇게 나옵니다")
    w("")
    w("같은 자료가 계획에 여러 번 나오면 **1권 첫 읽기 → 1권 다시 읽기 → 2권 첫 읽기 …** 순서로 진도가 나가고,")
    w("다음 계획은 이전 계획에서 멈춘 곳부터 이어갑니다. 예) `ort-stage2`의 처음 3일:")
    w("")
    for n in range(3):
        task, check = curriculum.unit_text("ort-stage2", n)
        w(f"{n + 1}. {task}  ")
        w(f"   확인 포인트: {check}")
    w("")
    songs = _load("songs.json")["songs"]
    w("## 오늘의 동요 (단계별 YouTube)")
    w("")
    w(f"계획 카드와 별도로, 오늘의 학습 화면에 **단계(L1~L5)에 맞는 영어 동요 1곡**을 날마다 안내합니다(총 {len(songs)}곡).")
    w("사흘에 한 번은 한 단계 아래 노래로 복습하고, 진단에서 알파벳을 모르는 아이는 L2(알파벳·글자 소리) 노래부터 듣습니다.")
    w("앱 안에서 재생하지 않고 **공식 채널 영상 링크**만 줍니다. 링크는 `python3 scripts/check_songs.py`로 채널을 확인합니다.")
    w("")
    for lv, (code, name) in LEVELS.items():
        rows = [s for s in songs if s["level"] == lv]
        w(f"<details><summary>{code} {name} — {len(rows)}곡</summary>")
        w("")
        w("| 노래 | 채널 | 길이 | 초점 | 부모와 함께 할 것 |")
        w("|---|---|---|---|---|")
        for s in rows:
            w(f"| [{s['title']}]({s['url']}) | {s['channel']} | 약 {s['minutes']}분 | {s['focus']} | {s['do']} |")
        w("")
        w("</details>")
        w("")
    w("## 출처와 원칙")
    w("")
    for key, text in g["unit_sources"].items():
        w(f"- 학습 단위 제목 출처 (`{key}`): {text}")
    w("- 출처(공식 목록 우선, 막힌 경우 명시한 2차 자료)에서 확인한 제목만 학습 단위로 넣습니다. 확인하지 못한 시리즈는 '묶음'으로 남겨 둡니다.")
    w("- 저작권(기획서 §7.3): 제목·팩 이름·활동 방법만 다루고 책 본문·영상·가사는 싣거나 호스팅하지 않습니다.")
    w("")
    w("## 남은 일 (묶음 → 학습 단위)")
    w("")
    rest = [it for it in catalog if items[it["id"]]["granularity"] == "collection"]
    w(f"아래 {len(rest)}개는 아직 '앱 전체·시리즈 전체' 단위라 카드가 막연합니다. 공식 목록으로 권·레슨을 확인해 단위로 쪼갤 대상입니다.")
    w("")
    w(", ".join(f"`{it['id']}`" for it in rest))
    w("")
    return "\n".join(L)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        try:
            with open(OUT, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = ""
        if current != text:
            print(f"{DOC_NAME}이 최신이 아닙니다: python3 scripts/gen_catalog_doc.py")
            return 1
        print(f"{DOC_NAME} 최신")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"작성: {DOC_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
