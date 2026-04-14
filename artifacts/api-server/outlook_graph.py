#!/usr/bin/env python3
"""
通过 Microsoft Graph API 读取 Outlook 邮件 OTP
使用 Device Code Flow 生成的 access_token / refresh_token
"""
import json, time, re, urllib.request, urllib.parse

CLIENT_ID  = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
TENANT     = "common"
TOKEN_FILE = "/tmp/ms_tokens.json"


def _refresh_access_token(refresh_token: str) -> str:
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "offline_access Mail.Read",
    }).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    if "access_token" not in resp:
        raise ValueError(f"刷新 token 失败: {resp}")
    # 保存新 token
    saved = {}
    try:
        with open(TOKEN_FILE) as f:
            saved = json.load(f)
    except Exception:
        pass
    saved["access_token"]  = resp["access_token"]
    saved["expires_at"]    = time.time() + resp.get("expires_in", 3600)
    if "refresh_token" in resp:
        saved["refresh_token"] = resp["refresh_token"]
    with open(TOKEN_FILE, "w") as f:
        json.dump(saved, f, indent=2)
    return resp["access_token"]


def _load_token() -> str:
    with open(TOKEN_FILE) as f:
        saved = json.load(f)
    if time.time() < saved.get("expires_at", 0) - 60:
        return saved["access_token"]
    return _refresh_access_token(saved["refresh_token"])


def _graph_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def wait_for_cursor_otp(timeout: int = 120) -> str | None:
    """
    轮询 Outlook 收件箱，返回 Cursor OTP 验证码（6位数字）。
    需要 /tmp/ms_tokens.json 存在（由 ms_device_auth.py 生成）。
    """
    import os
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            f"{TOKEN_FILE} 不存在，请先运行 ms_device_auth.py 完成授权"
        )
    deadline = time.time() + timeout
    seen_ids: set = set()
    token = _load_token()
    print("[outlook_graph] 开始轮询 Graph API 收件箱...")
    while time.time() < deadline:
        try:
            msgs = _graph_get(
                "/me/mailFolders/Inbox/messages"
                "?$top=15&$orderby=receivedDateTime+desc"
                "&$select=id,subject,bodyPreview,receivedDateTime,from",
                token,
            )
            for msg in msgs.get("value", []):
                mid = msg["id"]
                if mid in seen_ids:
                    continue
                subj = msg.get("subject", "")
                preview = msg.get("bodyPreview", "")
                if not re.search(r"cursor|verification|code|verify", subj + preview, re.I):
                    seen_ids.add(mid)
                    continue
                # 读完整正文
                detail = _graph_get(f"/me/messages/{mid}?$select=body", token)
                body   = detail.get("body", {}).get("content", "")
                m = re.search(r"(\d{6})", body)
                if m:
                    print(f"[outlook_graph] ✅ 找到 OTP: {m.group(1)}")
                    return m.group(1)
                seen_ids.add(mid)
        except Exception as e:
            print(f"[outlook_graph] 轮询异常: {e}")
            try:
                token = _load_token()
            except Exception:
                pass
        time.sleep(8)
    return None


if __name__ == "__main__":
    print(wait_for_cursor_otp(timeout=60))
