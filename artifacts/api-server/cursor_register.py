"""
Cursor.sh 账号自动注册脚本 v2 — 整合 j-cli CDP 网络拦截 + SheepKing 并发会话思想

新增特性:
  1. [j-cli CDP] 网络请求拦截：自动捕获 Cursor 认证 API 返回的 session token
  2. [j-cli snapshot] 页面快照元素检测：动态找表单字段，不依赖硬编码 CSS
  3. [SheepKing AgentSessionPool] 每个注册任务有独立 session，状态互不干扰

注册流程:
  1. 打开 cursor.sh signup 页面
  2. 安装网络拦截器（捕获 token）
  3. 用快照方式检测表单字段并填写
  4. 等待 OTP 验证码并填入
  5. 从网络拦截中提取 session token
"""

import argparse
import asyncio
import json
import random
import re
import secrets
import string
import sys
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse


# ─── 工具函数 ────────────────────────────────────────────────────────────────
def gen_password(n=None):
    n = n or random.randint(12, 16)
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = "".join(secrets.choice(chars) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*" for c in pw)):
            return pw


def gen_name():
    FIRST = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas",
             "Christopher","Daniel","Matthew","Anthony","Mark","Steven","Paul","Andrew","Joshua",
             "Benjamin","Samuel","Patrick","Jack","Tyler","Aaron","Nathan","Kyle","Bryan","Eric",
             "Mary","Patricia","Jennifer","Linda","Elizabeth","Susan","Jessica","Sarah","Karen",
             "Lisa","Nancy","Ashley","Emily","Donna","Michelle","Amanda","Melissa","Rebecca","Laura",
             "Emma","Olivia","Sophia","Isabella","Lucas","Ethan","Mason","Liam","Noah","Ava"]
    LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez",
             "Martinez","Hernandez","Lopez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson",
             "Lee","Perez","Thompson","White","Harris","Clark","Ramirez","Lewis","Robinson","Walker",
             "Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Green","Adams",
             "Nelson","Baker","Campbell","Mitchell","Carter","Turner","Phillips","Evans","Collins"]
    return random.choice(FIRST), random.choice(LAST)


def emit(type_: str, msg: str):
    line = json.dumps({"type": type_, "message": msg}, ensure_ascii=False)
    print(line, flush=True)


# ─── MailTM 临时邮箱 ─────────────────────────────────────────────────────────
MAILTM_BASE = "https://api.mail.tm"

def mailtm_create():
    try:
        r = urllib.request.urlopen(MAILTM_BASE + "/domains", timeout=10)
        domains = json.loads(r.read())
        domain = domains["hydra:member"][0]["domain"]
    except Exception:
        domain = "sharklasers.com"

    username = "cursor" + secrets.token_hex(6)
    email = f"{username}@{domain}"
    password = "CursorReg" + secrets.token_hex(4) + "!"

    data = json.dumps({"address": email, "password": password}).encode()
    req = urllib.request.Request(MAILTM_BASE + "/accounts", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
        emit("info", f"📧 临时邮箱创建: {email}")
    except Exception as e:
        emit("warn", f"邮箱创建异常: {e}，尝试登录...")

    data = json.dumps({"address": email, "password": password}).encode()
    req = urllib.request.Request(MAILTM_BASE + "/token", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=10)
    token_data = json.loads(r.read())
    return email, password, token_data["token"]


def mailtm_wait_otp(token: str, timeout: int = 90) -> str | None:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout
    seen = set()

    while time.time() < deadline:
        try:
            req = urllib.request.Request(MAILTM_BASE + "/messages", headers=headers)
            r = urllib.request.urlopen(req, timeout=10)
            msgs = json.loads(r.read())["hydra:member"]
            for msg in msgs:
                mid = msg["id"]
                if mid in seen:
                    continue
                seen.add(mid)
                req2 = urllib.request.Request(f"{MAILTM_BASE}/messages/{mid}", headers=headers)
                r2 = urllib.request.urlopen(req2, timeout=10)
                detail = json.loads(r2.read())
                body = detail.get("text", "") or detail.get("html", "")
                otp_match = re.search(r'\b(\d{6})\b', body)
                if otp_match:
                    otp = otp_match.group(1)
                    emit("info", f"✅ 收到验证码: {otp}")
                    return otp
        except Exception:
            pass
        time.sleep(3)

    return None


# ─── [j-cli CDP] 网络拦截：捕获 session token ───────────────────────────────
# 来自 LingoJack/j 的 CDP 思想：拦截浏览器网络响应，直接从 API 响应中提取 token
# j-cli 用 CDP 协议拦截所有 HTTP 响应；这里用 Playwright 的 response 事件实现相同效果

TOKEN_PATTERNS = [
    # Cursor API 返回的 token 字段名
    r'"accessToken"\s*:\s*"([^"]{20,})"',
    r'"access_token"\s*:\s*"([^"]{20,})"',
    r'"token"\s*:\s*"([^"]{20,})"',
    r'"sessionToken"\s*:\s*"([^"]{20,})"',
    r'"session_token"\s*:\s*"([^"]{20,})"',
    r'"jwt"\s*:\s*"([^"]{20,})"',
    r'"idToken"\s*:\s*"([^"]{20,})"',
    r'"id_token"\s*:\s*"([^"]{20,})"',
    r'"WorkosCursorSessionToken"\s*:\s*"([^"]{20,})"',
    r'"cursor_session_token"\s*:\s*"([^"]{20,})"',
]

# Cookie 中的 token 名称
TOKEN_COOKIE_NAMES = [
    "WorkosCursorSessionToken", "cursor_session_token", "session_token",
    "access_token", "auth_token", "__Secure-next-auth.session-token",
]

# 拦截的目标 URL 关键词
AUTH_URL_KEYWORDS = [
    "cursor.sh/api", "cursor.sh/auth", "cursor.sh/token",
    "authenticator.cursor.sh", "api2.cursor.sh",
    "/api/auth", "/oauth/token", "/sign-in", "/sign-up/callback",
    "workos.com/user_management", "workos.com/oauth",
]


def setup_network_intercept(page, session_state: dict):
    """
    [j-cli CDP 思想] 安装网络响应拦截器
    Playwright 的 page.on('response') 等价于 j-cli 的 CDP Network.responseReceived 事件
    捕获认证相关 API 返回的 token
    """
    async def on_response(response):
        try:
            url = response.url
            # 只关注认证相关 URL
            if not any(kw in url for kw in AUTH_URL_KEYWORDS):
                return
            if response.status not in (200, 201):
                return

            # 尝试读取响应体（JSON）
            try:
                body = await response.text()
            except Exception:
                return

            if not body or len(body) < 10:
                return

            # 在响应体中搜索 token
            for pattern in TOKEN_PATTERNS:
                m = re.search(pattern, body)
                if m:
                    token = m.group(1)
                    if len(token) > 20:
                        session_state["token"] = token
                        emit("info", f"🔑 [网络拦截] 捕获到 session token ({len(token)} chars) from {url}")
                        return

            # 尝试解析 JSON，查找嵌套 token
            try:
                data = json.loads(body)
                token = _extract_token_from_json(data)
                if token:
                    session_state["token"] = token
                    emit("info", f"🔑 [网络拦截] JSON 解析捕获到 token ({len(token)} chars) from {url}")
            except Exception:
                pass

        except Exception:
            pass

    page.on("response", on_response)
    emit("info", "🕵️ 网络拦截器已安装（将自动捕获 session token）")


def _extract_token_from_json(data, depth=0) -> str | None:
    """递归在 JSON 中寻找 token 字段"""
    if depth > 5:
        return None
    if isinstance(data, dict):
        for key in ("accessToken", "access_token", "token", "sessionToken",
                    "session_token", "jwt", "idToken", "id_token",
                    "WorkosCursorSessionToken", "cursor_session_token"):
            val = data.get(key)
            if isinstance(val, str) and len(val) > 20:
                return val
        for val in data.values():
            result = _extract_token_from_json(val, depth + 1)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_token_from_json(item, depth + 1)
            if result:
                return result
    return None


async def extract_token_from_cookies(page) -> str | None:
    """从浏览器 Cookie 中提取 token（最终兜底）"""
    try:
        cookies = await page.context.cookies()
        for cookie in cookies:
            if cookie.get("name") in TOKEN_COOKIE_NAMES:
                val = cookie.get("value", "")
                if len(val) > 20:
                    emit("info", f"🍪 从 Cookie 提取 token: {cookie['name']} ({len(val)} chars)")
                    return val
    except Exception:
        pass
    return None


# ─── [j-cli snapshot] 页面快照：动态发现表单字段 ────────────────────────────
# j-cli 的 snapshot() 函数扫描页面的所有可交互元素，为每个元素打上 data-jref 标记
# AI 读取快照后决定点击哪个元素。这里简化为：按语义关键字找输入框

async def page_snapshot(page) -> list[dict]:
    """
    [j-cli snapshot 思想] 获取页面所有可交互元素快照
    返回: [{ref, tag, type, placeholder, label, name, aria_label}]
    """
    try:
        elements = await page.evaluate("""
            () => Array.from(document.querySelectorAll(
                'input, button, [role="button"], textarea, select'
            )).slice(0, 60).map((el, i) => {
                const ref = 'r' + i;
                el.setAttribute('data-jref', ref);
                // 找关联 label
                let label = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.textContent.trim();
                }
                if (!label) {
                    const parent = el.closest('label, [class*="field"], [class*="form"]');
                    if (parent) label = parent.textContent.replace(el.value || '', '').trim().slice(0, 60);
                }
                return {
                    ref,
                    selector: `[data-jref="${ref}"]`,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || null,
                    name: el.name || null,
                    placeholder: el.placeholder || null,
                    aria_label: el.getAttribute('aria-label') || null,
                    label: label,
                    text: el.textContent?.trim().slice(0, 50) || null,
                    visible: el.offsetParent !== null,
                };
            })
        """)
        return elements
    except Exception:
        return []


async def find_input_smart(page, *keywords) -> str | None:
    """
    [j-cli snapshot 思想] 通过关键字语义搜索表单字段
    比硬编码 CSS 更鲁棒 — 即使 Cursor 改版也能找到
    返回 Playwright 兼容的 CSS selector
    """
    snapshot = await page_snapshot(page)
    kws = [k.lower() for k in keywords]

    for el in snapshot:
        if not el.get("visible"):
            continue
        # 把所有文本属性合并搜索
        haystack = " ".join(filter(None, [
            el.get("placeholder", ""), el.get("label", ""),
            el.get("aria_label", ""), el.get("name", ""), el.get("type", "")
        ])).lower()
        if any(kw in haystack for kw in kws):
            return el["selector"]

    return None


# ─── 主注册函数 ──────────────────────────────────────────────────────────────
async def register_one(proxy: str, headless: bool = True) -> dict | None:
    """
    注册单个 Cursor 账号
    [SheepKing AgentSessionPool] session_state 隔离每个注册任务的状态
    """
    start = time.time()

    # SheepKing 思想：每个任务有独立的 session 状态容器
    session_state = {
        "token": None,       # 网络拦截捕获的 session token
        "email": None,
        "password": None,
        "name": None,
    }

    first_name, last_name = gen_name()
    password = gen_password()

    try:
        email, _epw, mail_token = mailtm_create()
    except Exception as e:
        emit("error", f"❌ 临时邮箱创建失败: {e}")
        return None

    session_state.update({"email": email, "password": password, "name": f"{first_name} {last_name}"})
    emit("info", f"👤 {first_name} {last_name} | 📧 {email}")
    emit("info", "🌐 启动浏览器 → cursor.sh signup...")

    try:
        from patchright.async_api import async_playwright
    except ImportError:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            emit("error", "❌ 未安装 patchright/playwright")
            return None

    proxy_cfg = None
    if proxy:
        p = urlparse(proxy)
        proxy_cfg = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
        if p.username:
            proxy_cfg["username"] = p.username
            proxy_cfg["password"] = p.password or ""

    async with async_playwright() as pw:
        launch_opts = {
            "headless": headless,
            "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        }
        if proxy_cfg:
            launch_opts["proxy"] = proxy_cfg

        browser = await pw.chromium.launch(**launch_opts)
        ctx = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        # ── [j-cli CDP] 在任何导航之前安装网络拦截器 ──
        setup_network_intercept(page, session_state)

        try:
            # Step 1: 打开注册页面
            await page.goto("https://authenticator.cursor.sh/sign-up", timeout=60000,
                           wait_until="domcontentloaded")
            # 等 CF 挑战通过（最多 30s 轮询，每秒检测一次）
            emit("info", "⏳ 等待 CF 挑战通过（最多30s）…")
            _cf_start = __import__("time").time()
            while __import__("time").time() - _cf_start < 30:
                _url = page.url
                _title = await page.title()
                # CF 挑战页面：title 含 Just a moment 或 URL 没有变化到 sign-up
                if "Just a moment" not in _title and "challenge" not in _url.lower():
                    break
                await page.wait_for_timeout(1000)
            await page.wait_for_timeout(2000)
            emit("info", "📄 已打开注册页面")

            # Step 2: 填写姓名（快照方式 + CSS 降级）
            first_sel = await find_input_smart(page, "first", "name")
            if first_sel:
                await page.fill(first_sel, first_name)
                emit("info", f"👤 [快照] 填写名字: {first_name}")
                await page.wait_for_timeout(200)
            else:
                name_input = page.locator("input[name='first_name'], input[placeholder*='first' i], input[name='name']")
                if await name_input.count() > 0:
                    await name_input.first.fill(first_name)

            last_sel = await find_input_smart(page, "last")
            if last_sel:
                await page.fill(last_sel, last_name)
                emit("info", f"👤 [快照] 填写姓氏: {last_name}")
                await page.wait_for_timeout(200)
            else:
                last_input = page.locator("input[name='last_name'], input[placeholder*='last' i]")
                if await last_input.count() > 0:
                    await last_input.first.fill(last_name)

            # Step 3: 填写邮箱（快照方式）
            email_sel = await find_input_smart(page, "email", "mail")
            if email_sel:
                await page.fill(email_sel, email)
                emit("info", f"📧 [快照] 填写邮箱: {email}")
            else:
                email_input = page.locator("input[type='email'], input[name='email']")
                await email_input.first.wait_for(state="visible", timeout=30000)
                await email_input.first.fill(email)
                emit("info", f"📧 [CSS] 填写邮箱: {email}")
            await page.wait_for_timeout(500)

            # Step 4: 提交
            continue_btn = page.locator("button[type='submit'], button:has-text('Continue'), button:has-text('Sign up')")
            if await continue_btn.count() > 0:
                await continue_btn.first.click()
            else:
                await page.keyboard.press("Enter")
            emit("info", "⏳ 等待验证码邮件...")
            await page.wait_for_timeout(2000)

            # 并行等待 OTP
            otp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: mailtm_wait_otp(mail_token, timeout=90)
            )
            if not otp:
                emit("error", "❌ 超时未收到验证码邮件")
                await browser.close()
                return None

            # Step 5: 填入 OTP
            await page.wait_for_timeout(1000)
            otp_sel = await find_input_smart(page, "code", "otp", "verification", "one-time")
            if otp_sel:
                await page.fill(otp_sel, otp)
                emit("info", f"🔢 [快照] 填写验证码: {otp}")
                await page.wait_for_timeout(500)
                await page.keyboard.press("Enter")
            else:
                otp_input = page.locator(
                    "input[autocomplete='one-time-code'], input[type='text'][maxlength='6'], input[name='code']"
                )
                if await otp_input.count() > 0:
                    await otp_input.first.fill(otp)
                    await page.wait_for_timeout(500)
                    await otp_input.first.press("Enter")
                else:
                    digit_inputs = page.locator("input[maxlength='1']")
                    if await digit_inputs.count() >= 6:
                        for i, digit in enumerate(otp):
                            await digit_inputs.nth(i).fill(digit)
                            await page.wait_for_timeout(80)
                        await page.keyboard.press("Enter")
                    else:
                        await page.keyboard.type(otp, delay=100)
                        await page.keyboard.press("Enter")
                emit("info", f"🔢 [CSS] 填写验证码: {otp}")

            await page.wait_for_timeout(3000)

            # Step 6: 可能需要填写密码
            pw_sel = await find_input_smart(page, "password")
            if pw_sel:
                await page.fill(pw_sel, password)
                confirm_sel = await find_input_smart(page, "confirm", "repeat")
                if confirm_sel and confirm_sel != pw_sel:
                    await page.fill(confirm_sel, password)
                submit_btn = page.locator("button[type='submit']")
                if await submit_btn.count() > 0:
                    await submit_btn.first.click()
                    emit("info", "🔑 [快照] 已设置密码")
                await page.wait_for_timeout(2000)

            # Step 7: 等待网络拦截捕获 token（最多额外等 5s）
            for _ in range(10):
                if session_state["token"]:
                    break
                await page.wait_for_timeout(500)

            # 如果网络拦截没捕获到，从 Cookie 兜底
            if not session_state["token"]:
                session_state["token"] = await extract_token_from_cookies(page)

            # Step 8: 判断注册成功
            await page.wait_for_timeout(2000)
            current_url = page.url
            elapsed = round(time.time() - start, 1)

            if "sign-up" not in current_url and "error" not in current_url.lower():
                account = {
                    "email": email,
                    "password": password,
                    "name": f"{first_name} {last_name}",
                    "token": session_state["token"],
                }
                tok_display = f"token({len(session_state['token'])}chars)" if session_state["token"] else "无token"
                emit("success", f"✅ 注册成功 | {email} | {tok_display} | 耗时 {elapsed}s")
                await browser.close()
                return account
            else:
                await page.wait_for_timeout(3000)
                current_url = page.url
                if "sign-up" not in current_url:
                    account = {
                        "email": email,
                        "password": password,
                        "name": f"{first_name} {last_name}",
                        "token": session_state["token"],
                    }
                    emit("success", f"✅ 注册成功 | {email} | 耗时 {elapsed}s")
                    await browser.close()
                    return account
                else:
                    emit("error", f"❌ 注册失败，URL: {current_url}")
                    await browser.close()
                    return None

        except Exception as e:
            emit("error", f"❌ 注册异常: {type(e).__name__}: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return None


# ─── 主入口 ──────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--proxy", type=str, default="")
    parser.add_argument("--headless", type=str, default="true")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()

    headless = args.headless.lower() != "false"
    count = args.count
    success_count = 0
    accounts = []

    emit("info", f"🚀 Cursor 注册 v2 (CDP拦截+快照检测): {count}个 | 并发: {args.concurrency} | 代理: {args.proxy or '无'}")

    sem = asyncio.Semaphore(args.concurrency)

    async def limited_register():
        async with sem:
            return await register_one(proxy=args.proxy, headless=headless)

    tasks = [limited_register() for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, dict) and r:
            accounts.append(r)
            success_count += 1
        elif isinstance(r, Exception):
            emit("error", f"任务异常: {r}")

    emit("done", f"注册任务完成 · 成功 {success_count} 个 / 共 {count} 个 {'✅' if success_count else '❌'}")
    if accounts:
        emit("accounts", json.dumps(accounts, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
