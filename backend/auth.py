"""계정 인증: 이메일 ID + 비밀번호 (실명 인증 없음).

- 비밀번호: PBKDF2-HMAC-SHA256 (200,000회) + 계정별 salt + pepper. 원문은 절대 저장하지 않음.
- 로그인 토큰: HMAC-SHA256 서명, 만료 30일.
- 표준 라이브러리만 사용 (bcrypt 등 외부 의존성 없음).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

PEPPER = os.environ.get("BLOOMY_PEPPER", "bloomy-default-pepper").encode("utf-8")
TOKEN_TTL = 30 * 24 * 3600  # 30일
ITERATIONS = 200_000


def new_salt():
    return secrets.token_hex(16)


def hash_password(password, salt_hex):
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password + "|" + PEPPER.decode("utf-8")).encode("utf-8"),
        bytes.fromhex(salt_hex),
        ITERATIONS,
    )
    return digest.hex()


def make_token(account_id):
    payload = {"sub": account_id, "exp": int(time.time()) + TOKEN_TTL}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=")
    sig = base64.urlsafe_b64encode(
        hmac.new(PEPPER, body, hashlib.sha256).digest()
    ).rstrip(b"=")
    return (body + b"." + sig).decode("ascii")


def check_token(token):
    if not token:
        return None
    try:
        body_b64, sig_b64 = token.split(".")
        expected = hmac.new(PEPPER, body_b64.encode("ascii"), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(
            sig_b64.encode("ascii") + b"=" * (-len(sig_b64) % 4)
        )
        if not hmac.compare_digest(expected, actual):
            return None
        pad = "=" * (-len(body_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body_b64 + pad))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return int(payload["sub"])
    except Exception:
        return None
