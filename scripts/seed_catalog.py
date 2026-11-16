"""카탈로그 seed / 검증 스크립트 (01 §7.1-7.2, 11절 D4 게이트).

`catalog/*.json` (4인 분담: 각 15개, 총 60개) + 레거시 seed를 canonical 필드로
정규화해 DB(contents 테이블)에 멱등 업서트하고, 게이트 조건을 점검한다.

게이트 G3 (7.2): 총 45개 이상 **and** 나이별(4/5/6/7) 15개 이상
  (오픈 목표 60개 내외 — 게이트는 하한 45로 둔다)

실행:
  python scripts/seed_catalog.py           # DB 업서트 + 통계 출력
  python scripts/seed_catalog.py --check   # 검증만 (DB 안 쓸 수 있음, 게이트 실패 시 exit 1)
  python scripts/seed_catalog.py --strict  # 잘못된 항목 1개라도 있으면 실패
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import catalog  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Bloomy 카탈로그 seed/검증")
    ap.add_argument("--check", action="store_true",
                    help="검증만 하고 게이트 조건 통과 여부로 exit 코드 결정")
    ap.add_argument("--strict", action="store_true",
                    help="잘못된 항목 1개라도 있으면 실패")
    args = ap.parse_args()

    items, errors = catalog.validate()
    for e in errors:
        print("  ✗ %s" % e)
    st = catalog.stats(items)
    print("카탈로그 통계 (seed 파일 기준):")
    print("  total: %d (게이트: >=45, 나이별 >=15)" % st["total"])
    for age in (4, 5, 6, 7):
        mark = "ok" if st["by_age"][age] >= 15 else "미달"
        print("  %d세: %d [%s]" % (age, st["by_age"][age], mark))
    print("  레벨 분포: " + ", ".join(
        "L%d=%d" % (k, st["by_level"].get(k, 0)) for k in sorted(st["by_level"])))

    if args.check:
        if errors:
            print("\n결과: 실패 — %d개 항목 오류" % len(errors))
            return 1
        if not st["gate_ok"]:
            print("\n결과: 게이트 미달 (total>=45 & 나이별>=15 필요) — D4 게이트 통과 전")
            return 1
        print("\n결과: 게이트 통과 ✅")
        return 0

    n, load_errors = catalog.load(strict=args.strict)
    if load_errors:
        for e in load_errors:
            print("  (로딩 스킵) %s" % e)
    st2 = catalog.stats()
    print("\nDB 로드 완료: %d개 항목" % n)
    print("DB 게이트: %s" % ("통과 ✅" if st2["gate_ok"] else "미달 — 카탈로그 보강 필요"))
    return 0 if (st2["gate_ok"] or not args.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
