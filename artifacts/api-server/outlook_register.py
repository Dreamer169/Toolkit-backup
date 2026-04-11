"""
Outlook/Hotmail 批量注册自动化脚本
基于 patchright (增强版 Playwright，内置指纹伪装)
参考: https://github.com/hrhcode/outlook-batch-manager

用法:
  python3 outlook_register.py --count 5 --proxy socks5://127.0.0.1:1080 --output accounts.txt

注意: 在 Replit 无头环境中运行，已配置 headless=True + 指纹规避
"""

import argparse
import asyncio
import json
import random
import secrets
import string
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── 人名库 ──────────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles",
    "Christopher","Daniel","Matthew","Anthony","Mark","Donald","Steven","Paul","Andrew","Joshua",
    "Kenneth","Kevin","Brian","George","Timothy","Ronald","Edward","Jason","Jeffrey","Ryan",
    "Jacob","Gary","Nicholas","Eric","Jonathan","Stephen","Larry","Justin","Scott","Brandon",
    "Benjamin","Samuel","Frank","Alexander","Patrick","Jack","Dennis","Jerry","Tyler","Aaron",
    "Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica","Sarah","Karen",
    "Lisa","Nancy","Betty","Margaret","Sandra","Ashley","Dorothy","Kimberly","Emily","Donna",
    "Michelle","Amanda","Melissa","Deborah","Stephanie","Rebecca","Sharon","Laura","Cynthia","Amy",
    "Emma","Olivia","Noah","Liam","Ava","Sophia","Isabella","Mia","Charlotte","Amelia",
    "Lucas","Ethan","Mason","Logan","Aiden","Jackson","Sebastian","Oliver","Elijah","Owen",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
    "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
    "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
    "Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
    "Turner","Phillips","Evans","Edwards","Collins","Stewart","Morris","Murphy","Cook","Rogers",
    "Bennett","Gray","Hughes","Price","Patel","Parker","Butler","Barnes","Fisher","Henderson",
    "Hacker","Dev","Code","Fox","Wolf","Stone","Drake","Blake","Chase","Quinn",
]


def pick(arr): return random.choice(arr)
def rand(a, b): return random.randint(a, b)


def gen_username():
    fn = pick(FIRST_NAMES)
    ln = pick(LAST_NAMES)
    year2 = str(rand(70, 99))
    year4 = str(rand(1975, 2000))
    num2  = str(rand(10, 99))
    num3  = str(rand(100, 999))
    patterns = [
        fn + ln,
        fn + ln + year2,
        fn.lower() + "." + ln.lower(),
        fn.lower() + ln.lower() + num2,
        fn[0].lower() + ln.lower() + year2,
        fn.lower() + "_" + ln.lower(),
        fn.lower() + "_" + ln.lower() + num2,
        fn + ln + num3,
        fn.lower() + year4,
        fn[0].lower() + "." + ln.lower() + num2,
        ln.lower() + fn.lower() + num2,
        fn[0].lower() + ln.lower() + num3,
    ]
    return pick(patterns), fn, ln


def gen_password(n=None):
    n = n or rand(12, 16)
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = "".join(secrets.choice(chars) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*" for c in pw)):
            return pw


def gen_birthdate():
    year  = rand(1975, 2000)
    month = rand(1, 12)
    day   = rand(1, 28)
    return year, month, day


# ─── Playwright 注册器 ────────────────────────────────────────────────────────
class OutlookRegistrar:
    def __init__(self, proxy=None, headless=True, slow_mo=800, timeout=60):
        self.proxy    = proxy
        self.headless = headless
        self.slow_mo  = slow_mo
        self.timeout  = timeout * 1000  # ms

    async def register_one(self, username: str, password: str, first: str, last: str,
                           year: int, month: int, day: int) -> dict:
        try:
            from patchright.async_api import async_playwright
        except ImportError:
            from playwright.async_api import async_playwright

        result = {"username": username, "email": f"{username}@outlook.com",
                  "password": password, "success": False, "error": "", "time": ""}

        async with async_playwright() as p:
            launch_kw: dict = {
                "headless": self.headless,
                "slow_mo": self.slow_mo,
                "args": [
                    "--lang=en-US,en",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            }
            if self.proxy:
                launch_kw["proxy"] = {"server": self.proxy}

            browser = await p.chromium.launch(**launch_kw)
            context = await browser.new_context(
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": rand(1280, 1920), "height": rand(768, 1080)},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"Chrome/12{rand(0,5)}.0.0.0 Safari/537.36"
                ),
            )

            # 注入 stealth JS: 隐藏 webdriver 标记
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            t0 = time.time()

            try:
                # ── Step 1: 导航到注册页 ──────────────────────────
                print(f"  [1/6] Opening signup page for {username}@outlook.com")
                await page.goto("https://signup.live.com/signup", timeout=self.timeout)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(rand(1, 2))

                # ── Step 2: 填写用户名 ────────────────────────────
                print(f"  [2/6] Filling username: {username}")
                uname_sel = 'input[name="MemberName"], input[id="MemberName"], input[aria-label*="mail"]'
                await page.wait_for_selector(uname_sel, timeout=15000)
                await page.fill(uname_sel, username)
                await asyncio.sleep(rand(1, 2))

                # 域名选择 outlook.com (如果有下拉)
                try:
                    domain_sel = 'select[id="LiveDomainBoxList"]'
                    if await page.query_selector(domain_sel):
                        await page.select_option(domain_sel, "outlook.com")
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                await page.keyboard.press("Tab")
                await asyncio.sleep(rand(1, 2))
                next_btn = 'input[value="Next"], button:has-text("Next"), button:has-text("下一步")'
                await page.click(next_btn, timeout=8000)
                await asyncio.sleep(rand(1, 2))

                # ── Step 3: 填写密码 ──────────────────────────────
                print(f"  [3/6] Filling password")
                pw_sel = 'input[name="Password"], input[type="password"]'
                await page.wait_for_selector(pw_sel, timeout=10000)
                await page.fill(pw_sel, password)
                await asyncio.sleep(rand(1, 2))
                await page.click(next_btn, timeout=8000)
                await asyncio.sleep(rand(1, 2))

                # ── Step 4: 填写姓名 ──────────────────────────────
                print(f"  [4/6] Filling name: {first} {last}")
                fn_sel = 'input[id="FirstName"], input[name="FirstName"], input[aria-label*="First"]'
                ln_sel = 'input[id="LastName"], input[name="LastName"], input[aria-label*="Last"]'
                await page.wait_for_selector(fn_sel, timeout=10000)
                await page.fill(fn_sel, first)
                await asyncio.sleep(0.5)
                await page.fill(ln_sel, last)
                await asyncio.sleep(rand(1, 2))
                await page.click(next_btn, timeout=8000)
                await asyncio.sleep(rand(1, 2))

                # ── Step 5: 填写生日 ──────────────────────────────
                print(f"  [5/6] Filling birthdate: {month}/{day}/{year}")
                try:
                    country_sel = 'select[id="Country"]'
                    if await page.query_selector(country_sel):
                        await page.select_option(country_sel, "US")
                        await asyncio.sleep(0.5)
                    birth_month = 'select[id="BirthMonth"]'
                    birth_day   = 'select[id="BirthDay"]'
                    birth_year  = 'input[id="BirthYear"]'
                    await page.select_option(birth_month, str(month))
                    await asyncio.sleep(0.3)
                    await page.select_option(birth_day, str(day))
                    await asyncio.sleep(0.3)
                    await page.fill(birth_year, str(year))
                    await asyncio.sleep(rand(1, 2))
                    await page.click(next_btn, timeout=8000)
                    await asyncio.sleep(rand(2, 3))
                except Exception as e:
                    print(f"  [5/6] Birthdate warning: {e}")

                # ── Step 6: 处理验证码 / 等待完成 ─────────────────
                print(f"  [6/6] Checking for CAPTCHA or completion...")
                current_url = page.url
                if "account/intro" in current_url or "outlook.com" in current_url:
                    result["success"] = True
                    result["time"] = f"{time.time()-t0:.1f}s"
                    print(f"  ✅ REGISTERED: {username}@outlook.com ({result['time']})")
                else:
                    # 可能还有验证码或额外步骤
                    try:
                        # 等待成功跳转或错误
                        await page.wait_for_url("**/account/intro**", timeout=30000)
                        result["success"] = True
                        result["time"] = f"{time.time()-t0:.1f}s"
                        print(f"  ✅ REGISTERED: {username}@outlook.com ({result['time']})")
                    except Exception:
                        # 截图便于调试
                        screenshot_path = f"/tmp/outlook_fail_{username}.png"
                        await page.screenshot(path=screenshot_path)
                        result["error"] = f"未能完成注册 (可能有验证码), 截图: {screenshot_path}"
                        print(f"  ❌ FAILED: {result['error']}")

            except Exception as e:
                result["error"] = str(e)
                print(f"  ❌ ERROR: {e}")

            finally:
                await browser.close()

        return result


# ─── 主程序 ───────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Outlook 批量注册工具")
    parser.add_argument("--count",    type=int, default=1,   help="注册数量")
    parser.add_argument("--proxy",    type=str, default="",  help="代理地址, 如 socks5://127.0.0.1:1080")
    parser.add_argument("--output",   type=str, default="",  help="输出文件 (默认仅打印)")
    parser.add_argument("--headless", type=str, default="true", help="true/false")
    parser.add_argument("--delay",    type=int, default=3,   help="每次注册间隔秒数")
    args = parser.parse_args()

    headless = args.headless.lower() != "false"
    registrar = OutlookRegistrar(proxy=args.proxy or None, headless=headless)
    results = []

    print(f"\n🚀 Outlook 批量注册 — 共 {args.count} 个账号\n{'─'*50}")

    for i in range(args.count):
        username, first, last = gen_username()
        password = gen_password()
        year, month, day = gen_birthdate()

        print(f"\n[{i+1}/{args.count}] 注册: {username}@outlook.com | {first} {last} | 生日: {year}/{month}/{day}")
        result = await registrar.register_one(username, password, first, last, year, month, day)
        result.update({"firstName": first, "lastName": last, "birthYear": year, "birthMonth": month, "birthDay": day})
        results.append(result)

        if i < args.count - 1:
            delay = args.delay + rand(0, 3)
            print(f"  ⏱ 等待 {delay}s 再注册下一个...")
            await asyncio.sleep(delay)

    # ── 汇总 ──────────────────────────────────────────────
    ok  = [r for r in results if r["success"]]
    bad = [r for r in results if not r["success"]]
    print(f"\n{'─'*50}")
    print(f"✅ 成功: {len(ok)} / {len(results)}")
    for r in ok:
        print(f"  📧 {r['email']}  密码: {r['password']}")
    if bad:
        print(f"❌ 失败: {len(bad)}")
        for r in bad:
            print(f"  {r['email']}: {r['error']}")

    if args.output:
        Path(args.output).write_text(
            "\n".join(f"{r['email']}----{r['password']}" for r in ok)
        )
        print(f"\n💾 已保存 {len(ok)} 条到 {args.output}")

    # JSON 结果打印 (供其他脚本调用)
    print("\n── JSON ──")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
