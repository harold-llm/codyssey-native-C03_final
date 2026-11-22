"""자동화 워크플로우 (01 §6.5) — 서버리스 크론 대응 + 로컬 데몬.

운영: Vercel 크론(1회/일, 무료 티어) → POST /api/cron job=daily → run_daily()
  run_daily가 내부에서 조건 분기해 일괄 처리:
    ① 오늘 학습 카드 발송 (매일 아침)
    ② 어젯셈 미기록 리마인더 — 1회만 (meta 중복 방지, 부드러운 톤)
    ③ 일요일 → 지난 주(월~일) 주간 리포트
    ④ 1일 → 전월 학습 성취 리포트 (요금 무관)

로컬 개발: start() 데몬 스레드가 같은 시간표로 tick()한다.
중복 발송 방지는 meta 테이블의 날짜 키(`daily:{child}:{date}` 등)로 처리.
"""
import datetime as dt
import os
import threading
import time
from typing import cast

import catalog
import clock
import coach

import store


def _parse_hhmm(s: object) -> tuple[int, int]:
    try:
        hh, mm = str(s).split(":")
        return int(hh), int(mm)
    except Exception:  # noqa: BLE001
        return 9, 0


DAILY_HH, DAILY_MM = _parse_hhmm(os.environ.get("BLOOMY_DAILY_TIME", "09:00"))
REMIND_HH, REMIND_MM = 21, 0
WEEKLY_WEEKDAY, WEEKLY_HH = 6, 18  # 일요일 18:00
MONTHLY_DAY, MONTHLY_HH = 1, 10    # 1일 10:00


def _nick(child: dict[str, object]) -> str:
    return str(child.get("name") or "우리 아이")


def _notify(
    child: dict[str, object], title: str, body: str, kind: str = "info",
) -> None:
    cid = cast("int", child["id"])
    acc = store.get_user_by_child(cid)
    if acc:
        uid = cast("int", acc["id"])
        _ = store.add_notification(uid, title, body, kind)


def _item(card: dict[str, object] | None) -> catalog.Item | None:
    if card and card.get("content_id"):
        return catalog.find_item(card["content_id"])
    return None


# ---------------------------------------------------------------------------
# 잡
# ---------------------------------------------------------------------------

def daily(date: str | None = None) -> None:
    """매일 아침: 오늘 학습 카드 발송 (pending → sent)."""
    today = date or clock.today().isoformat()
    for child in store.all_children():
        cid = cast("int", child["id"])
        key = f"daily:{cid}:{today}"
        if store.meta_get(key):
            continue
        card = store.get_card_for_child(cid, today)
        if not card:
            continue
        store.meta_set(key, "1")
        if card["status"] == "pending":
            store.set_card_status(cast("int", card["id"]), "sent")
        item = _item(card)
        minutes = cast("int", card["minutes"])
        body = (
            f"{_nick(child)}의 오늘 학습\n{card['task']}\n"
            f"{minutes}분\n\n"
            "함께 한 뒤에는 앱에서 오늘의 기록(완료도·만족도·흥미·이해도)을 "
            "남겨주세요. 코치가 바로 반응할게요."
        )
        if card.get("check_point"):
            body += f"\n확인 포인트: {card['check_point']}"
        if item:
            if item.get("link"):
                body += f"\n링크: {item['link']}"
            if item.get("provider") == "purchase":
                body += "\n교재 제공 방식 — 집에 있는지 먼저 확인해 주세요."
            if item.get("expert_note"):
                body += f"\nTIP: {item['expert_note'][:120]}"
        _notify(child, f"오늘의 학습 · {_nick(child)}", body, kind="daily")


def remind(date: str | None = None) -> None:
    """해당 날 미기록 시 부드러운 리마인드 — 1회만 (meta 키로 중복 방지).

    Vercel 무료 플랜은 크론이 하루 1회라, 다음 날 아침 run_daily가
    어젯셈의 미기록을 대신 확인하는 '캐치업' 용도로도 호출된다."""
    target = date or (clock.today() - dt.timedelta(days=1)).isoformat()
    for child in store.all_children():
        cid = cast("int", child["id"])
        key = f"remind:{cid}:{target}"
        if store.meta_get(key):
            continue
        if store.get_feedback(cid, target):
            continue
        card = store.get_card_for_child(cid, target)
        if not card:
            continue
        store.meta_set(key, "1")
        body = (
            "그날 학습 기록이 아직 없어요. 1분이면 충분해요.\n"
            "기록을 남겨주시면 코치가 다음 날 카드 조정까지 준비할게요.\n"
            "(쉬어간 날이면 기록에서 '휴식일'로 표시해 주세요 — 성취에서 제외돼요.)"
        )
        _notify(child, f"기록 리마인드 · {_nick(child)}", body, kind="remind")


def weekly(date: str | None = None) -> None:
    """일요일: 지난 주(월~일) 주간 리포트. 확신 문구는 데이터 조건부 (6.6)."""
    d = dt.date.fromisoformat(date) if date else clock.today()
    if d.weekday() != 6:  # 일요일만
        return
    ws = d - dt.timedelta(days=7)  # 지난 주 월요일
    for child in store.all_children():
        cid = cast("int", child["id"])
        key = f"weekly:{cid}:{ws.isoformat()}"
        if store.meta_get(key):
            continue
        store.meta_set(key, "1")
        report = coach.weekly_report(child, ws.isoformat())
        if report["record_days"]:
            parts: list[str] = [str(report["summary"])]
            if report["learned"]:
                learned = cast("list[str]", report["learned"])
                parts.append(f"이번 주에 한층 잘하게 된 것: {', '.join(learned)}")
            if report["confidence_sentence"]:
                parts.append(str(report["confidence_sentence"]))
            if report["honest_note"]:
                parts.append(str(report["honest_note"]))
            choices = cast("list[str]", report["choices"])
            parts.append(f"다음 주 선택지: {' / '.join(choices)}")
            if report["next_cards"]:
                cards = cast("list[dict[str, object]]", report["next_cards"])
                card_lines = [
                    f"{c['date']} {c['task']}({c['minutes']}분)"
                    for c in cards[:3]
                ]
                parts.append(f"다음 주 카드: {'; '.join(card_lines)}")
            parts.append(str(report["one_step"]))
            body = "\n".join(parts)
        else:
            body = ("지난 주에는 학습 기록이 아직 없어요. "
                    "이번 주 첫 학습일 아침, 10분 첫걸음을 함께 내딛어볼까요?")
        _notify(child, f"주간 리포트 · {_nick(child)}", body, kind="report")


def monthly(date: str | None = None) -> None:
    """1일: 전월 학습 성취 리포트 — 요금·청구와 무관하게 성취만 (5.5)."""
    d = dt.date.fromisoformat(date) if date else clock.today()
    if d.day != 1:  # 1일만
        return
    month = (d - dt.timedelta(days=1)).strftime("%Y-%m")
    for child in store.all_children():
        cid = cast("int", child["id"])
        key = f"monthly:{cid}:{month}"
        if store.meta_get(key):
            continue
        store.meta_set(key, "1")
        ach = coach.monthly_achievement(child, month)
        head = (
            f"지난 달 학습: {ach['record_days']}일, "
            f"최장 {ach['max_streak']}일 연속."
        )
        parts: list[str] = [head]
        if ach["learned"]:
            parts.append(f"새로 익은 것: {', '.join(ach['learned'][:3])}")
        if ach["avg_interest"] is not None:
            avg_line = (
                f"흥미 평균 {ach['avg_interest']:.1f} · "
                f"이해도 평균 {ach['avg_comprehension']:.1f}."
            )
            parts.append(avg_line)
        parts.append(ach["note"])
        _notify(
            child, f"월간 성취 리포트 · {_nick(child)}", "\n".join(parts),
            kind="report",
        )


def run_daily(date: str | None = None) -> None:
    """Vercel daily 크론 단일 진입점 (6.5 무료 티어 1회/일 대응).

    ① 카드 발송 → ② 어젯셈 미기록 리마인더 → ③(일요일) 주간 → ④(1일) 월간.
    """
    d = dt.date.fromisoformat(date) if date else clock.today()
    daily(date=d.isoformat())
    remind(date=(d - dt.timedelta(days=1)).isoformat())
    if d.weekday() == 6:
        weekly(date=d.isoformat())
    if d.day == 1:
        monthly(date=d.isoformat())


# ---------------------------------------------------------------------------
# 로컬 개발용 루프
# ---------------------------------------------------------------------------

def tick() -> None:
    """한 번의 스케줄 검사. (스모크 테스트에서 직접 호출할 수도 있다.)"""
    now = clock.now()
    if (now.hour, now.minute) >= (DAILY_HH, DAILY_MM):
        daily()
    if (now.hour, now.minute) >= (REMIND_HH, REMIND_MM):
        remind()
    if now.weekday() == WEEKLY_WEEKDAY and now.hour >= WEEKLY_HH:
        weekly()
    if now.day == MONTHLY_DAY and now.hour >= MONTHLY_HH:
        monthly()


def start(interval: float = 60) -> threading.Thread:
    """데몬 스레드로 스케줄러 시작. 반환: Thread"""

    def loop() -> None:
        while True:
            try:
                tick()
            except Exception as exc:  # noqa: BLE001
                print(f"[bloomy-scheduler] tick error: {exc}")
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=True, name="bloomy-scheduler")
    t.start()
    return t
