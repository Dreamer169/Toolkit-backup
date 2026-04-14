#!/usr/bin/env python3
"""
Cursor.sh HTTP 注册器 — 无浏览器、纯 HTTP 协议

流程 (5步):
  1. 获取 session / state
  2. 提交邮箱 (Next.js Server-Action)
  3. 提交密码 + Turnstile token
  4. 轮询邮件取 OTP -> 提交 OTP 换 auth_code
  5. 回调 cursor.com 拿 WorkosCursorSessionToken

用法:
  python cursor_register_http.py \
    --email  user@example.com \
    --password Abc.1234567890 \
    --proxy  http://user:pass@host:port \
    --imap-host imap.example.com --imap-user user --imap-pass pass \
    --captcha-service yescaptcha --captcha-key YOUR_KEY
"""

import argparse
import base64
import hashlib
import imaplib
import email as email_lib
import json
import os
import random
import re
import secrets
import string
import sys
import time

import httpx

CURSOR_AUTH_BASE  = "https://authenticator.cursor.sh"
CURSOR_BASE       = "https://cursor.com"

ACTION_SUBMIT_EMAIL    = "d0b05a2a36fbe69091c2f49016138171d5c1e4cd"
ACTION_SUBMIT_PASSWORD = "fef846a39073c935bea71b63308b177b113269b7"
ACTION_MAGIC_CODE      = "f9e8ae3d58a7cd11cccbcdbf210e6f2a6a2550dd"

TURNSTILE_SITE_KEY = "0x4AAAAAAAMNIvC45A4Wjjln"

NEXT_ROUTER_STATE = (
    "%5B%22%22%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B"
    "%22(root)%22%2C%7B%22children%22%3A%5B%22(sign-in)%22%2C%7B%22children%22"
    "%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%5D%7D%5D"
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


def rand_str(n: int) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))


def rand_password(n: int = 16) -> str:
    lower = random.choice(string.ascii_lowercase)
    upper = random.choice(string.ascii_uppercase)
    digit = random.choice(string.digits)
    sym   = '.'
    rest  = ''.join(random.choices(string.ascii_letters + string.digits, k=n - 4))
    chars = list(lower + upper + digit + sym + rest)
    random.shuffle(chars)
    return ''.join(chars)


def build_pkce() -> tuple:
    verifier  = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return verifier, challenge


def build_state() -> str:
    verifier, challenge = build_pkce()
    state_obj = {
        "returnTo": "/",
        "crypto": {
            "id":             rand_str(22),
            "code_challenge": challenge,
            "code_verifier":  verifier,
        },
        "createdAt": int(time.time() * 1000),
    }
    raw = json.dumps(state_obj, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def build_multipart(fields: dict) -> tuple:
    boundary = "----WebKitFormBoundary" + rand_str(16)
    parts = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
        )
    body = (''.join(parts) + f'--{boundary}--\r\n').encode()
    ct   = f'multipart/form-data; boundary={boundary}'
    return body, ct


def action_headers(action_hash: str, referer: str, content_type: str) -> dict:
    return {
        "User-Agent":             UA,
        "Accept":                 "text/x-component",
        "Content-Type":           content_type,
        "Origin":                 CURSOR_AUTH_BASE,
        "Referer":                referer,
        "Next-Action":            action_hash,
        "Next-Router-State-Tree": NEXT_ROUTER_STATE,
    }


def solve_turnstile(service: str, api_key: str, page_url: str, site_key: str) -> str:
    if not api_key:
        raise ValueError("未配置打码 API key，Turnstile 无法绕过")
    s = service.lower().replace('-', '').replace('_', '')

    if s == "yescaptcha":
        r = httpx.post("https://api.yescaptcha.com/createTask", json={
            "clientKey": api_key,
            "task": {
                "type": "TurnstileTaskProxylessM1",
                "websiteURL": page_url,
                "websiteKey": site_key,
            }
        }, timeout=30).json()
        if r.get("errorId", 1) != 0:
            raise RuntimeError(f"YesCaptcha 提交失败: {r}")
        task_id = r["taskId"]
        for _ in range(60):
            time.sleep(5)
            res = httpx.post("https://api.yescaptcha.com/getTaskResult",
                             json={"clientKey": api_key, "taskId": task_id},
                             timeout=15).json()
            if res.get("status") == "ready":
                return res["solution"]["token"]
        raise TimeoutError("YesCaptcha Turnstile 超时")

    if s in ("capsolver", "cap_solver"):
        r = httpx.post("https://api.capsolver.com/createTask", json={
            "clientKey": api_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
            }
        }, timeout=30).json()
        if r.get("errorId", 0) != 0:
            raise RuntimeError(f"CapSolver 提交失败: {r}")
        task_id = r["taskId"]
        for _ in range(60):
            time.sleep(5)
            res = httpx.post("https://api.capsolver.com/getTaskResult",
                             json={"clientKey": api_key, "taskId": task_id},
                             timeout=15).json()
            if res.get("status") == "ready":
                return res["solution"]["token"]
        raise TimeoutError("CapSolver Turnstile 超时")

    if s == "2captcha":
        resp = httpx.post("https://2captcha.com/in.php", data={
            "key": api_key, "method": "turnstile",
            "sitekey": site_key, "pageurl": page_url, "json": 1,
        }, timeout=30).json()
        task_id = resp.get("request")
        for _ in range(72):
            time.sleep(5)
            res = httpx.get("https://2captcha.com/res.php",
                            params={"key": api_key, "action": "get",
                                    "id": task_id, "json": 1},
                            timeout=15).json()
            if res.get("status") == 1:
                return res["request"]
        raise TimeoutError("2captcha Turnstile 超时")

    raise ValueError(f"未知打码服务: {service}，支持 yescaptcha / capsolver / 2captcha")


def wait_for_otp_imap(host: str, user: str, password: str,
                      timeout: int = 180, interval: int = 5) -> str:
    deadline = time.time() + timeout
    print(f"[IMAP] 等待 Cursor OTP 邮件 ({host})...", flush=True)
    while time.time() < deadline:
        try:
            m = imaplib.IMAP4_SSL(host, timeout=10)
            m.login(user, password)
            m.select("INBOX")
            _, ids = m.search(None, 'SUBJECT "Cursor" UNSEEN')
            for num in (ids[0].split() or []):
                _, data = m.fetch(num, "(RFC822)")
                msg  = email_lib.message_from_bytes(data[0][1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                match = re.search(r'\b(\d{6})\b', body)
                if match:
                    m.logout()
                    return match.group(1)
            m.logout()
        except Exception as e:
            print(f"[IMAP] 连接错误: {e}", flush=True)
        time.sleep(interval)
    raise TimeoutError("等待 OTP 超时")


class CursorRegistrar:
    def __init__(self, proxy=None):
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        self.client = httpx.Client(
            proxies=proxies, follow_redirects=False, timeout=30,
            headers={"User-Agent": UA},
        )
        self.client_follow = httpx.Client(
            proxies=proxies, follow_redirects=True, timeout=60,
            headers={"User-Agent": UA},
        )

    def step1_get_session(self, state_encoded: str):
        url = (f"{CURSOR_AUTH_BASE}/sign-up?client_id=cursor-editor"
               f"&redirect_uri={CURSOR_BASE}/auth/callback"
               f"&response_type=code&state={state_encoded}")
        r = self.client_follow.get(url)
        print(f"[Step1] GET session -> {r.status_code}", flush=True)
        if r.status_code not in (200, 302, 303):
            raise RuntimeError(f"Step1 异常: {r.status_code}")

    def step2_submit_email(self, email: str, state_encoded: str):
        body, ct = build_multipart({"1_state": state_encoded, "email": email})
        url  = f"{CURSOR_AUTH_BASE}/sign-up"
        hdrs = action_headers(ACTION_SUBMIT_EMAIL, url, ct)
        r    = self.client.post(url, content=body, headers=hdrs)
        print(f"[Step2] 提交邮箱 -> {r.status_code}", flush=True)
        if r.status_code not in (200,):
            raise RuntimeError(f"Step2 异常: {r.status_code} {r.text[:200]}")

    def step3_submit_password(self, email: str, password: str,
                               state_encoded: str, captcha_token: str):
        body, ct = build_multipart({
            "1_state":      state_encoded,
            "email":        email,
            "password":     password,
            "captchaToken": captcha_token,
        })
        url  = f"{CURSOR_AUTH_BASE}/sign-up"
        hdrs = action_headers(ACTION_SUBMIT_PASSWORD, url, ct)
        r    = self.client.post(url, content=body, headers=hdrs)
        print(f"[Step3] 提交密码 -> {r.status_code}", flush=True)
        if r.status_code not in (200,):
            raise RuntimeError(f"Step3 异常: {r.status_code} {r.text[:200]}")

    def step4_submit_otp(self, email: str, otp: str, state_encoded: str) -> str:
        body, ct = build_multipart({
            "1_state": state_encoded,
            "email":   email,
            "otp":     otp,
        })
        url  = f"{CURSOR_AUTH_BASE}/sign-up"
        hdrs = action_headers(ACTION_MAGIC_CODE, url, ct)
        r    = self.client.post(url, content=body, headers=hdrs)
        print(f"[Step4] 提交 OTP -> {r.status_code}", flush=True)
        loc = r.headers.get("location", "")
        if not loc:
            m = re.search(r'code=([A-Za-z0-9_\-]+)', r.text)
            if m:
                return m.group(1)
            raise RuntimeError(f"Step4: 未找到 auth code, body={r.text[:300]}")
        m = re.search(r'code=([A-Za-z0-9_\-]+)', loc)
        if not m:
            raise RuntimeError(f"Step4: location 中无 code: {loc!r}")
        return m.group(1)

    def step5_get_token(self, auth_code: str, state_encoded: str) -> str:
        cb = (f"{CURSOR_BASE}/auth/callback"
              f"?code={auth_code}&state={state_encoded}")
        r = self.client_follow.get(cb)
        print(f"[Step5] 获取 token -> {r.status_code}", flush=True)
        for cookie in self.client_follow.cookies.jar:
            if cookie.name == "WorkosCursorSessionToken":
                return cookie.value
        raise RuntimeError("Step5: 未找到 WorkosCursorSessionToken cookie")

    def close(self):
        self.client.close()
        self.client_follow.close()


def register(email: str, password: str, proxy,
             captcha_service: str, captcha_key: str,
             imap_host: str, imap_user: str, imap_pass: str) -> dict:
    state_encoded = build_state()
    reg = CursorRegistrar(proxy=proxy)
    try:
        print(f"[Cursor] 注册 {email} ...", flush=True)
        reg.step1_get_session(state_encoded)
        reg.step2_submit_email(email, state_encoded)

        print("[Cursor] 解 Turnstile...", flush=True)
        captcha_token = solve_turnstile(
            captcha_service, captcha_key,
            f"{CURSOR_AUTH_BASE}/sign-up", TURNSTILE_SITE_KEY
        )
        print(f"[Cursor] Turnstile token 长度={len(captcha_token)}", flush=True)

        reg.step3_submit_password(email, password, state_encoded, captcha_token)

        otp = wait_for_otp_imap(imap_host, imap_user, imap_pass)
        print(f"[Cursor] OTP={otp}", flush=True)

        auth_code     = reg.step4_submit_otp(email, otp, state_encoded)
        session_token = reg.step5_get_token(auth_code, state_encoded)

        print(f"[Cursor] SUCCESS email={email} token_len={len(session_token)}", flush=True)
        return {
            "success":  True,
            "email":    email,
            "password": password,
            "token":    session_token,
        }
    finally:
        reg.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cursor HTTP 注册器")
    p.add_argument("--email",           default="")
    p.add_argument("--password",        default="")
    p.add_argument("--proxy",           default="")
    p.add_argument("--captcha-service", default=os.environ.get("CAPTCHA_SERVICE", "yescaptcha"))
    p.add_argument("--captcha-key",     default=os.environ.get("CAPTCHA_KEY", ""))
    p.add_argument("--imap-host",       default=os.environ.get("IMAP_HOST", ""))
    p.add_argument("--imap-user",       default=os.environ.get("IMAP_USER", ""))
    p.add_argument("--imap-pass",       default=os.environ.get("IMAP_PASS", ""))
    args = p.parse_args()

    if not args.email:
        try:
            from faker import Faker
            fk   = Faker()
            name = fk.user_name() + str(random.randint(10, 99))
            args.email = f"{name}@outlook.com"
        except ImportError:
            args.email = f"cursor_{rand_str(8)}@outlook.com"
    if not args.password:
        args.password = rand_password()

    result = register(
        email           = args.email,
        password        = args.password,
        proxy           = args.proxy or None,
        captcha_service = args.captcha_service,
        captcha_key     = args.captcha_key,
        imap_host       = args.imap_host,
        imap_user       = args.imap_user,
        imap_pass       = args.imap_pass,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
