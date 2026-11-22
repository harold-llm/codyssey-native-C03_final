"""개인정보 수집·이용 동의 (미션 AI 윤리 · 기획서 8.4 · NFR-05).

가입 시 두 항목 동의를 필수로 받고 버전·시각을 기록한다.
동의 철회 = 계정 탈퇴이며, 계정과 아이 관련 데이터를 즉시 모두 삭제한다.
"""
from __future__ import annotations

CONSENT_VERSION = "2026-11-23"

NOTICE: dict[str, object] = {
    "version": CONSENT_VERSION,
    "title": "개인정보 수집·이용 동의",
    "items": [
        {"label": "수집 항목",
         "value": "보호자: 이메일, 비밀번호(단방향 해시로만 저장) · 아이: 닉네임, 나이, "
                  "영어 노출·관심사·학습 시간, 진단 5문항 응답, 매일의 학습 기록과 메모"},
        {"label": "이용 목적",
         "value": "맞춤 학습 계획 생성, 매일의 AI 코칭 메시지, 주간·월간 학습 리포트"},
        {"label": "AI 처리",
         "value": "학습 기록과 메모는 코칭 문장 생성을 위해 외부 AI 서비스(Anthropic Claude)로 "
                  "전송될 수 있습니다. 이메일·비밀번호는 전송하지 않습니다."},
        {"label": "보관 기간",
         "value": "탈퇴(동의 철회) 시까지. 탈퇴하면 계정과 아이의 모든 기록을 즉시 삭제합니다."},
        {"label": "동의 거부",
         "value": "동의를 거부할 수 있으나, 거부 시 서비스 가입이 불가합니다."},
    ],
    "required": {
        "agree_privacy": "개인정보 수집·이용 및 AI 처리에 동의합니다 (필수)",
        "agree_guardian": "만 14세 미만 아이의 법정대리인(보호자)으로서 아이 정보 수집에 동의합니다 (필수)",
    },
}


def missing(body: dict[str, object]) -> list[str]:
    """가입 요청에서 동의하지 않은 필수 항목 키 목록 (True만 동의로 인정)."""
    required = NOTICE["required"]
    assert isinstance(required, dict)
    return [k for k in required if body.get(k) is not True]
