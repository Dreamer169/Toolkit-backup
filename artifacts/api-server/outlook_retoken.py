#!/usr/bin/env python3
"""
outlook_retoken.py — Outlook 账号自动浏览器重新授权
用 patchright 打开浏览器，登录账号，完成 device code OAuth 授权。
不需要人工介入。

用法:
  python3 outlook_retoken.py --ids 2,3,4     # 指定账号 ID
  python3 outlook_retoken.py --all-error      # 所有 error 状态账号
  python3 outlook_retoken.py --all-error --headless false  # 可视化模式
"""

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/toolkit")

# 优先用 Thunderbird client_id（与现有系统一致），fallback 到 Azure CLI
CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
TENANT    = "consumers"
SCOPE     = "offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/User.Read"


def log(msg: str):
    print(msg, flush=True)


def db_conn():
    return psycopg2.connect(DATABASE_URL)


def get_accounts(ids: list[int] | None, all_error: bool) -> list[dict]:
    conn = db_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if ids:
        cur.execute(
            "SELECT id, email, password FROM accounts WHERE platform='outlook' AND id = ANY(%s) AND password IS NOT NULL AND password != ''",
            (ids,),
        )
    elif all_error:
        cur.execute(
            "SELECT id, email, password FROM accounts WHERE platform='outlook' AND status='error' AND password IS NOT NULL AND password != '' ORDER BY id"
        )
    else:
        cur.execute(
            "SELECT id, email, password FROM accounts WHERE platform='outlook' AND (token IS NULL OR token='') AND password IS NOT NULL AND password != '' ORDER BY id"
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def save_tokens(account_id: int, access_token: str, refresh_token: str):
    conn = db_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE accounts SET token=%s, refresh_token=%s, status='active', updated_at=NOW() WHERE id=%s",
        (access_token, refresh_token, account_id),
    )
    conn.commit()
    conn.close()


def request_device_code() -> dict:
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope":     SCOPE,
    }).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/devicecode",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return resp  # {device_code, user_code, verification_uri, interval, expires_in, ...}


def poll_token(device_code: str, interval: int = 5, expires_in: int = 900) -> dict | None:
    deadline = time.time() + expires_in
    data = urllib.parse.urlencode({
        "client_id":    CLIENT_ID,
        "grant_type":   "urn:ietf:params:oauth:grant-type:device_code",
        "device_code":  device_code,
    }).encode()
    while time.time() < deadline:
        time.sleep(interval)
        req = urllib.request.Request(
            f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            continue
        if resp.get("access_token"):
            return resp
        err = resp.get("error", "")
        if err in ("authorization_pending", "slow_down"):
            if err == "slow_down":
                time.sleep(interval)
            continue
        log(f"  ❌ token 轮询失败: {resp.get('error_description', err)[:120]}")
        return None
    log("  ❌ 设备码已过期")
    return None


async def retoken_account(account: dict, headless: bool, proxy: str = "") -> bool:
    email    = account["email"]
    password = account["password"]
    acc_id   = account["id"]

    log(f"\n{'='*60}")
    log(f"[{acc_id}] 开始处理: {email}")

    # 1. 申请设备码
    try:
        dc = request_device_code()
    except Exception as e:
        log(f"  ❌ 申请设备码失败: {e}")
        return False

    user_code        = dc["user_code"]
    device_code_val  = dc["device_code"]
    verification_uri = dc.get("verification_uri", "https://microsoft.com/devicelogin")
    interval         = dc.get("interval", 5)
    expires_in       = dc.get("expires_in", 900)
    log(f"  🔑 设备码: {user_code}  URL: {verification_uri}")

    # 2. 启动 patchright 浏览器
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log("  ❌ 未安装 patchright/playwright")
            return False

    # 在后台线程中轮询 token（与浏览器操作并行）
    token_result: list[dict | None] = [None]
    token_done = asyncio.Event()

    async def poll_background():
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, poll_token, device_code_val, interval, expires_in)
        token_result[0] = result
        token_done.set()

    poll_task = asyncio.create_task(poll_background())

    async with async_playwright() as p:
        launch_args: dict = {
            "headless": headless,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        }
        if proxy:
            launch_args["proxy"] = {"server": proxy}

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            locale="zh-CN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        try:
            # 3. 导航到 devicelogin 页面
            log(f"  🌐 打开: {verification_uri}")
            await page.goto(verification_uri, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # 4. 输入 user_code
            code_input = page.locator('input[name="otc"], input[id="otc"], input[type="text"]').first
            await code_input.wait_for(timeout=10000)
            await code_input.fill(user_code)
            log(f"  ✍️  输入用户码: {user_code}")
            await asyncio.sleep(1)

            # 点击 Next/继续
            next_btn = page.locator('input[type="submit"], button[type="submit"]').first
            await next_btn.click()
            await asyncio.sleep(3)

            # 5. 可能需要登录 — 输入 email
            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            try:
                _email_visible = await email_input.is_visible(timeout=5000)
            except Exception:
                _email_visible = False
            if _email_visible:
                await email_input.fill(email)
                log(f"  📧 输入邮箱: {email}")
                await asyncio.sleep(1)
                next_btn2 = page.locator('input[type="submit"], button[type="submit"]').first
                await next_btn2.click()
                await asyncio.sleep(3)

            # 6. 输入密码
            pw_input = page.locator('input[type="password"], input[name="passwd"]').first
            if await pw_input.is_visible(timeout=8000):
                await pw_input.fill(password)
                log("  🔒 输入密码")
                await asyncio.sleep(1)
                sign_btn = page.locator('input[type="submit"], button[type="submit"]').first
                await sign_btn.click()
                await asyncio.sleep(4)
            else:
                log("  ⚠️  密码框未出现，可能已登录或被拦截")

            # 7. 处理 "Stay signed in?" (KMSI)
            kmsi = page.locator('input[type="submit"][value*="Yes"], button:has-text("Yes"), button:has-text("是")').first
            if await kmsi.is_visible(timeout=4000):
                await kmsi.click()
                log("  ✅ 点击了 '保持登录'")
                await asyncio.sleep(2)

            # 8. 处理 consent 页面 — 点击 Approve/继续/Accept
            # 截图调试（同意前）
            try:
                await page.screenshot(path=f"/tmp/retoken_{acc_id}_consent.png")
                log(f"  📸 截图已保存: /tmp/retoken_{acc_id}_consent.png | URL: {page.url[:80]}")
            except Exception:
                pass

            # 扩展同意按钮选择器：中英文 + 批准
            # 参考 hrhcode/outlook-batch-manager: appConsentPrimaryButton
            try:
                await page.locator('[data-testid="appConsentPrimaryButton"]').click(timeout=12000)
                log("  ✅ 点击 appConsentPrimaryButton 同意授权")
                await asyncio.sleep(3)
            except Exception:
                log(f"  ℹ️  未检测到同意按钮，URL: {page.url[:80]}")

            # 检查是否有错误提示
            error_div = page.locator('[id*="error"], .alert-error, [aria-live="assertive"]').first
            if await error_div.is_visible(timeout=2000):
                err_text = await error_div.inner_text()
                log(f"  ⚠️  页面提示: {err_text[:120]}")

            log("  ⏳ 等待 token 轮询结果…")
            # 等待最多120秒
            try:
                await asyncio.wait_for(token_done.wait(), timeout=120)
            except asyncio.TimeoutError:
                log("  ❌ 等待 token 超时")

        except Exception as e:
            log(f"  ❌ 浏览器操作异常: {e}")
        finally:
            await browser.close()

    # 取消轮询任务（如果还在跑）
    if not poll_task.done():
        poll_task.cancel()

    tok = token_result[0]
    if tok and tok.get("access_token"):
        save_tokens(acc_id, tok["access_token"], tok.get("refresh_token", ""))
        log(f"  ✅ Token 已保存！email={email}")
        return True
    else:
        log(f"  ❌ 未能获取 token")
        return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids",        default="",    help="逗号分隔的账号 ID 列表")
    parser.add_argument("--all-error",  action="store_true", help="处理所有 status=error 的账号")
    parser.add_argument("--headless",   default="true", help="true/false")
    parser.add_argument("--proxy",      default="",    help="代理地址")
    parser.add_argument("--concurrency",type=int, default=1, help="并发数（建议1-3）")
    args = parser.parse_args()

    headless = args.headless.lower() != "false"
    ids_list = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else None

    accounts = get_accounts(ids_list, args.all_error)
    if not accounts:
        log("没有找到需要处理的账号（确保账号有密码）")
        return

    log(f"共 {len(accounts)} 个账号需要重新授权，并发={args.concurrency}")

    ok_count  = 0
    fail_count = 0

    # 按并发数分批处理
    sem = asyncio.Semaphore(args.concurrency)

    async def process_one(acc):
        nonlocal ok_count, fail_count
        async with sem:
            success = await retoken_account(acc, headless, args.proxy)
            if success:
                ok_count += 1
            else:
                fail_count += 1

    await asyncio.gather(*[process_one(a) for a in accounts])

    log(f"\n{'='*60}")
    log(f"完成！成功: {ok_count} / 失败: {fail_count} / 总计: {len(accounts)}")


if __name__ == "__main__":
    asyncio.run(main())
