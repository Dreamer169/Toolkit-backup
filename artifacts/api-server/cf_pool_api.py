#!/usr/bin/env python3
"""
CF IP 池命令行 API（被 tools.ts 通过 spawnSync 调用）
用法：
  python3 cf_pool_api.py status
  python3 cf_pool_api.py refresh [--count N] [--target N] [--threads N] [--port N] [--max-latency N]
  python3 cf_pool_api.py acquire --job-id JOB_ID
  python3 cf_pool_api.py release --job-id JOB_ID
"""
import sys, json, argparse, os

sys.path.insert(0, os.path.dirname(__file__))
import cf_ip_pool

POOL_STATE_FILE = '/tmp/cf_pool_state.json'

def _load_pool_from_disk():
    """每次新进程启动时从磁盘恢复池状态到内存"""
    try:
        with open(POOL_STATE_FILE) as f:
            state = json.load(f)
        available = state.get('available', [])
        history   = state.get('history', [])
        with cf_ip_pool._pool_lock:
            cf_ip_pool._available.clear()
            cf_ip_pool._available.extend(available)
            cf_ip_pool._used_history.clear()
            cf_ip_pool._used_history.extend(history)
    except Exception:
        pass  # 文件不存在或损坏，保持空池

def cmd_status(args):
    try:
        with open(POOL_STATE_FILE) as f:
            state = json.load(f)
        available = state.get('available', [])
        used_total = len(state.get('history', []))
    except Exception:
        available = []
        used_total = 0
    print(json.dumps({
        'available': len(available),
        'pool': available[:20],
        'used_total': used_total,
    }))

def cmd_refresh(args):
    _load_pool_from_disk()
    logs = []
    new_ips = cf_ip_pool.refresh_pool(
        generate_count = args.count,
        target_valid   = args.target,
        threads        = args.threads,
        port           = args.port,
        max_latency    = args.max_latency,
        log_cb         = lambda m: logs.append(m),
    )
    _persist_history()
    try:
        with open(POOL_STATE_FILE) as f:
            state = json.load(f)
        total_available = len(state.get('available', []))
    except Exception:
        total_available = len(new_ips)
    print(json.dumps({
        'new_ips': len(new_ips),
        'total_available': total_available,
        'pool': new_ips[:20],
        'logs': logs,
    }))

def _persist_history():
    """把 _used_history 也写入 JSON，供下次进程恢复"""
    try:
        try:
            with open(POOL_STATE_FILE) as f:
                state = json.load(f)
        except Exception:
            state = {}
        with cf_ip_pool._pool_lock:
            state['available']     = cf_ip_pool._available[:]
            state['history']       = cf_ip_pool._used_history[:]
            state['history_count'] = len(cf_ip_pool._used_history)
        with open(POOL_STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception:
        pass

def cmd_acquire(args):
    _load_pool_from_disk()           # ← 关键修复：先加载磁盘状态
    ip_info = cf_ip_pool.acquire_ip(args.job_id, auto_refresh=True)
    _persist_history()               # ← 写回 history，防止重用
    if ip_info:
        print(json.dumps({'success': True, **ip_info}))
    else:
        print(json.dumps({'success': False, 'error': '池中无可用 IP'}))

def cmd_release(args):
    _load_pool_from_disk()
    cf_ip_pool.release_ip(args.job_id)
    _persist_history()
    print(json.dumps({'success': True}))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('status')
    ref = sub.add_parser('refresh')
    ref.add_argument('--count',       type=int,   default=60)
    ref.add_argument('--target',      type=int,   default=20)
    ref.add_argument('--threads',     type=int,   default=5)
    ref.add_argument('--port',        type=int,   default=443)
    ref.add_argument('--max-latency', type=float, default=800.0, dest='max_latency')
    acq = sub.add_parser('acquire')
    acq.add_argument('--job-id', required=True, dest='job_id')
    rel = sub.add_parser('release')
    rel.add_argument('--job-id', required=True, dest='job_id')
    args = p.parse_args()
    if   args.cmd == 'status':  cmd_status(args)
    elif args.cmd == 'refresh': cmd_refresh(args)
    elif args.cmd == 'acquire': cmd_acquire(args)
    elif args.cmd == 'release': cmd_release(args)
    else: print(json.dumps({'error': 'unknown command'}))
