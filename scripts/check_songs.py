"""동요 링크 확인 — 각 영상이 살아 있고 공식 채널에 올라와 있는지 YouTube oEmbed로 검사한다.

네트워크가 필요하므로 smoke test에는 넣지 않는다. 링크를 추가·변경할 때 실행:
    python3 scripts/check_songs.py
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 카드에 보이는 채널명 → YouTube 공식 채널 표시 이름(앞부분)
OFFICIAL = {
    "Super Simple Songs": "Super Simple Songs",
    "Super Simple ABCs": "Super Simple ABCs",
    "Jack Hartmann": "Jack Hartmann",
    "Have Fun Teaching": "Have Fun Teaching",
    "Alphablocks": "Alphablocks",
    "Pinkfong": "Baby Shark - Pinkfong",
}


def check(song: dict) -> str | None:
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(song["url"], safe="")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "bloomy-link-check"}), timeout=15) as r:
            info = json.load(r)
    except Exception as exc:  # noqa: BLE001
        return f"열리지 않음 ({exc})"
    author = info.get("author_name", "")
    if not author.startswith(OFFICIAL.get(song["channel"], "\0")):
        return f"채널 불일치: {author!r}"
    return None


def main() -> int:
    songs = json.loads((ROOT / "backend/data/songs.json").read_text(encoding="utf-8"))["songs"]
    bad = 0
    for s in songs:
        err = check(s)
        if err:
            bad += 1
            print(f"FAIL {s['id']}: {err}")
    print(f"{len(songs) - bad}/{len(songs)} OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
