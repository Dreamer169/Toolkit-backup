"""
ChatGPT 批量注册工具 — Web 管理界面
Flask 后端: 配置管理 / 任务控制 / SSE 实时日志 / 账号管理 / OAuth 导出
"""

import os
import io
import csv
import json
import time
import queue
import zipfile
import threading
from datetime import datetime
from flask import Flask, request, jsonify, Response, render_template, send_file

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
ACCOUNTS_FILE = os.path.join(BASE_DIR, "registered_accounts.txt")
ACCOUNTS_CSV = os.path.join(BASE_DIR, "registered_accounts.csv")
AK_FILE = os.path.join(BASE_DIR, "ak.txt")
RK_FILE = os.path.join(BASE_DIR, "rk.txt")
TOKEN_DIR = os.path.join(BASE_DIR, "codex_tokens")

# ── Task state ──────────────────────────────────────────────
_task_lock = threading.Lock()
_task_running = False
_task_thread = None
_task_stop_event = threading.Event()
_task_progress = {"total": 0, "done": 0, "success": 0, "fail": 0}

# ── SSE log broadcast ──────────────────────────────────────
_log_subscribers: list[queue.Queue] = []
_log_lock = threading.Lock()
_recent_logs: list[str] = []
_recent_log_limit = 200

def _broadcast_log(line: str):
    with _log_lock:
        _recent_logs.append(line)
        if len(_recent_logs) > _recent_log_limit:
            del _recent_logs[:len(_recent_logs) - _recent_log_limit]
        dead = []
        for q in _log_subscribers:
            try:
                q.put_nowait(line)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _log_subscribers.remove(q)

class _LogCapture(io.TextIOBase):
    """Captures print() output and broadcasts via SSE while also writing to real stdout."""
    def __init__(self, real_stdout):
        self._real = real_stdout
    def write(self, s):
        if s and s.strip():
            _broadcast_log(s.rstrip("\n\r"))
        return self._real.write(s)
    def flush(self):
        return self._real.flush()

# ── Config helpers ──────────────────────────────────────────
def _read_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

# ── Account helpers ─────────────────────────────────────────
def _parse_accounts():
    accounts = []
    if not os.path.exists(ACCOUNTS_FILE):
        return accounts
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            parts = line.split("----")
            acc = {
                "index": i,
                "email": parts[0] if len(parts) > 0 else "",
                "password": parts[1] if len(parts) > 1 else "",
                "email_password": parts[2] if len(parts) > 2 else "",
                "oauth_status": parts[3] if len(parts) > 3 else "",
                "raw": line,
            }
            accounts.append(acc)
    return accounts

def _write_accounts(accounts):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        for acc in accounts:
            f.write(acc["raw"] + "\n")


# ═══════════════════════════  ROUTES  ═══════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ── Config ──────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(_read_config())

@app.route("/api/config", methods=["POST"])
def save_config():
    cfg = request.get_json(force=True)
    _write_config(cfg)
    return jsonify({"ok": True})


# ── Task control ────────────────────────────────────────────
@app.route("/api/start", methods=["POST"])
def start_task():
    global _task_running, _task_thread, _task_progress
    with _task_lock:
        if _task_running:
            return jsonify({"ok": False, "error": "任务正在运行中"}), 409

    body = request.get_json(force=True) or {}
    count = int(body.get("count", 1))
    workers = int(body.get("workers", 1))
    proxy = body.get("proxy", "").strip() or None

    _task_stop_event.clear()
    _task_progress = {"total": count, "done": 0, "success": 0, "fail": 0}

    def _run():
        global _task_running
        import sys
        real_stdout = sys.__stdout__
        sys.stdout = _LogCapture(real_stdout)
        try:
            # Reload config_loader with fresh config
            import importlib
            import config_loader
            importlib.reload(config_loader)
            config_loader.run_batch(
                total_accounts=count,
                output_file="registered_accounts.txt",
                max_workers=workers,
                proxy=proxy,
            )
        except Exception as e:
            import traceback
            _broadcast_log(f"❌ 任务异常: {e}")
            _broadcast_log(traceback.format_exc())
        finally:
            sys.stdout = real_stdout
            with _task_lock:
                _task_running = False
            _broadcast_log("__TASK_DONE__")

    _task_running = True
    _task_thread = threading.Thread(target=_run, daemon=True)
    _task_thread.start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop_task():
    global _task_running
    _task_stop_event.set()
    # Force stop isn't trivial for threads; we set a flag.
    _broadcast_log("⚠️ 收到停止指令，将在当前账号完成后停止")
    return jsonify({"ok": True})


@app.route("/api/status", methods=["GET"])
def task_status():
    return jsonify({
        "running": _task_running,
        "progress": _task_progress,
    })


# ── SSE Logs ────────────────────────────────────────────────
@app.route("/api/logs")
def sse_logs():
    q = queue.Queue(maxsize=500)
    with _log_lock:
        _log_subscribers.append(q)
        history = list(_recent_logs)

    def stream():
        try:
            for msg in history:
                yield f"data: {msg}\n\n"
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _log_lock:
                if q in _log_subscribers:
                    _log_subscribers.remove(q)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Accounts ────────────────────────────────────────────────
@app.route("/api/accounts", methods=["GET"])
def list_accounts():
    return jsonify(_parse_accounts())


@app.route("/api/accounts", methods=["DELETE"])
def delete_accounts():
    body = request.get_json(force=True) or {}
    indices = set(body.get("indices", []))
    mode = body.get("mode", "selected")  # "all" or "selected"

    accounts = _parse_accounts()
    if mode == "all":
        _write_accounts([])
        return jsonify({"ok": True, "deleted": len(accounts)})

    remaining = [a for a in accounts if a["index"] not in indices]
    _write_accounts(remaining)
    return jsonify({"ok": True, "deleted": len(accounts) - len(remaining)})


# ── OAuth Export ────────────────────────────────────────────
@app.route("/api/export", methods=["POST"])
def export_oauth():
    """
    Export individual <email>.json token files from codex_tokens/ as a ZIP.
    - mode: "all" → include every file in codex_tokens/
    - mode: "selected" → only include files whose content contains one of the selected emails
    """
    body = request.get_json(force=True) or {}
    mode = body.get("mode", "all")          # "all" or "selected"
    indices = set(body.get("indices", []))

    # Resolve the email list to filter against
    if mode == "selected":
        accounts = _parse_accounts()
        target_emails = {a["email"] for a in accounts if a["index"] in indices}
    else:
        target_emails = None  # None = include all

    if not os.path.isdir(TOKEN_DIR):
        return jsonify({"error": "codex_tokens 目录不存在"}), 404

    buf = io.BytesIO()
    exported = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(TOKEN_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(TOKEN_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as tf:
                    content = tf.read()
            except Exception:
                continue

            # Filtering: if selected mode, check if this file's email matches
            if target_emails is not None:
                # Try to match by filename (email is the filename stem)
                stem = fname[:-5]  # remove .json
                matched = any(em in stem or em in content for em in target_emails)
                if not matched:
                    continue

            # Write directly at ZIP root: <email>.json
            zf.writestr(fname, content)
            exported += 1

    if exported == 0:
        return jsonify({"error": f"没有找到匹配的 Token 文件（共扫描 codex_tokens/）"}), 404

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"codex_tokens_{ts}.zip"
    )



# ── 代绑订阅余额查询 ──────────────────────────────────────
@app.route("/api/sub-balance", methods=["POST"])
def sub_balance():
    """查询代绑订阅 API 余额"""
    body = request.get_json(force=True) or {}
    api_key = body.get("api_key", "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "请填写 API Key"}), 400
    try:
        import requests as std_requests
        resp = std_requests.get(
            "https://sub.zenscaleai.com/api/v1/balance",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        return jsonify({"ok": True, "data": resp.json(), "status": resp.status_code})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── Team 母号注册 ──────────────────────────────────────────
@app.route("/api/register-master", methods=["POST"])
def register_master():
    """注册 Team 母号 → 代绑订阅 → 获取 Team 信息 → 自动导入"""
    global _task_running, _task_thread
    with _task_lock:
        if _task_running:
            return jsonify({"ok": False, "error": "有任务正在运行中"}), 409

    body = request.get_json(force=True) or {}
    api_key = body.get("api_key", "").strip()
    card = body.get("card", "").strip()
    plan = body.get("plan", "team").strip()
    proxy = body.get("proxy", "").strip() or None
    card_number = body.get("card_number", "").strip()  # 用于标记已使用

    if not api_key:
        return jsonify({"ok": False, "error": "请填写 API Key"}), 400
    if not card:
        return jsonify({"ok": False, "error": "请填写卡信息"}), 400

    _task_stop_event.clear()

    def _run():
        global _task_running
        import sys
        real_stdout = sys.__stdout__
        sys.stdout = _LogCapture(real_stdout)
        try:
            import importlib
            import config_loader
            importlib.reload(config_loader)

            # 1. 注册账号
            _broadcast_log("### 📝 开始注册 Team 母号 ###")
            reg_result = config_loader.register_team_master(proxy=proxy)

            if not reg_result.get("access_token"):
                _broadcast_log("❌ 注册成功但未获取到 AccessToken，无法继续")
                return

            # 2. 调用代绑订阅 API
            _broadcast_log("### 💳 调用代绑订阅 API ###")
            import requests as std_requests
            try:
                sub_resp = std_requests.post(
                    "https://sub.zenscaleai.com/api/v1/subscribe",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "access_token": reg_result["access_token"],
                        "card": card,
                        "plan": plan,
                    },
                    timeout=120,
                )
                sub_data = sub_resp.json()
                _broadcast_log(f"订阅响应: {json.dumps(sub_data, ensure_ascii=False)}")

                if not sub_data.get("success"):
                    _broadcast_log(f"❌ 订阅失败: {sub_data.get('error', '未知错误')}")
                    return

                _broadcast_log(f"✅ 订阅绑定成功! 计划: {sub_data.get('plan', plan)}")
            except Exception as e:
                _broadcast_log(f"❌ 订阅 API 请求异常: {e}")
                return

            # 3. 等待订阅生效
            _broadcast_log("⏳ 等待订阅生效 (5秒)...")
            time.sleep(5)

            # 4. 获取 Team 信息
            _broadcast_log("### 🔍 获取 Team 信息 ###")
            session_token = reg_result.get("session_token", "")
            team_info = config_loader.get_team_info_from_session(session_token, proxy=proxy)

            if not team_info or not team_info.get("account_id"):
                _broadcast_log("⚠️ 未能获取 Team 信息，使用基础信息创建")
                payload = config_loader._decode_jwt_payload(reg_result["access_token"])
                auth_info = payload.get("https://api.openai.com/auth", {})
                fallback_id = auth_info.get("chatgpt_account_id", "")
                team_info = {
                    "name": f"Team-{fallback_id[:8]}",
                    "account_id": fallback_id,
                    "auth_token": reg_result["access_token"],
                    "session_token": session_token,
                }

            # 5. 导入到 config.json
            new_team = {
                "name": team_info.get("name", "New Team"),
                "account_id": team_info.get("account_id", ""),
                "auth_token": team_info.get("auth_token", ""),
                "session_token": team_info.get("session_token", ""),
                "max_invites": 5,
            }
            cfg = _read_config()
            if "teams" not in cfg:
                cfg["teams"] = []
            cfg["teams"].append(new_team)
            _write_config(cfg)

            # 6. 标记卡为已使用
            if card_number:
                cfg2 = _read_config()
                for c in cfg2.get("cards", []):
                    if c.get("number", "").strip() == card_number:
                        c["used"] = True
                        break
                _write_config(cfg2)

            _broadcast_log(f"✅ Team 信息已导入!")
            _broadcast_log(f"   Team 名称: {new_team['name']}")
            _broadcast_log(f"   Account ID: {new_team['account_id']}")
            _broadcast_log(f"   Auth Token: {new_team['auth_token'][:50]}...")
            _broadcast_log(f"   Session Token: {(new_team['session_token'] or '')[:50]}...")
            _broadcast_log(f"### 🎉 Team 母号注册全流程完成! ###")

        except Exception as e:
            import traceback
            _broadcast_log(f"❌ 母号注册异常: {e}")
            _broadcast_log(traceback.format_exc())
        finally:
            sys.stdout = real_stdout
            with _task_lock:
                _task_running = False
            _broadcast_log("__TASK_DONE__")

    _task_running = True
    _task_thread = threading.Thread(target=_run, daemon=True)
    _task_thread.start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("🚀 ChatGPT 注册管理面板启动: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
