# ChatGPT Team 一键注册工具

## 项目概述

ChatGPT Team 一键注册工具是一个功能完整的 Web 管理界面，用于批量注册 ChatGPT Team 账号。支持多种临时邮箱服务、代理配置、OAuth 自动授权，以及 Token 导出功能。

## 功能特性

- **批量注册** - 支持多线程批量注册 ChatGPT Team 账号
- **多种邮箱服务** - 支持 GPTMail、NPCMail 等临时邮箱服务
- **代理支持** - 可配置代理 IP 进行注册
- **OAuth 自动授权** - 自动完成 OAuth 登录获取 Token
- **Web 管理界面** - 可视化界面，实时显示注册进度和日志
- **账号管理** - 查看、删除已注册的账号
- **Token 导出** - 导出 OAuth Token 为 ZIP 文件
- **Sub2Api 上传** - 支持将 Token 上传到 Sub2Api 平台

## 项目结构

```
team_all-in-one/
├── app.py               # Flask Web 服务主程序
├── config.json          # 配置文件
├── config_loader.py     # 配置加载器
├── ak.txt               # Access Key 存储
├── rk.txt               # Refresh Key 存储
├── registered_accounts.txt  # 注册账号存储
├── registered_accounts.csv # CSV 格式账号存储
├── invite_tracker.json  # 邀请追踪
├── codex_tokens/        # OAuth Token 存储目录
├── static/              # 静态资源
│   ├── style.css
│   └── mac_style.css
└── templates/
    └── index.html       # 前端页面
```

## 环境要求

- Python 3.10+
- Flask

## 快速开始

### 1. 安装依赖

```bash
pip install flask
```

### 2. 配置 config.json

```json
{
    "mail_provider": "gptmail",
    "gptmail_base": "https://mail.chatgpt.org.uk",
    "gptmail_api_key": "your-api-key",
    "npcmail_api_key": "",
    "npcmail_domain": "git-hub.email",
    "proxy": "",
    "enable_oauth": true,
    "oauth_issuer": "https://auth.openai.com",
    "oauth_client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
    "SUB2API_URL": "",
    "SUB2API_TOKEN": "",
    "sub_api_key": "",
    "sub_plan": "team",
    "default_address": {
        "street": "",
        "city": "",
        "state": "",
        "zip": "",
        "country": ""
    },
    "cards": [],
    "teams": []
}
```

### 3. 配置说明

| 配置项 | 说明 |
|--------|------|
| `mail_provider` | 邮箱服务提供商：`gptmail` 或 `npcmail` |
| `gptmail_api_key` | GPTMail API 密钥 |
| `npcmail_api_key` | NPCMail API 密钥 |
| `npcmail_domain` | NPCMail 域名 |
| `proxy` | 代理地址 |
| `enable_oauth` | 是否启用 OAuth 自动授权 |
| `SUB2API_URL` | Sub2Api 平台 URL |
| `SUB2API_TOKEN` | Sub2Api 平台 Token |
| `sub_plan` | 订阅计划：`team` 或 `plus` |

### 4. 启动服务

```bash
python app.py
```

服务启动后访问 `http://localhost:5000`

## Web 界面功能

- **任务控制** - 启动/停止批量注册任务
- **实时日志** - SSE 实时显示注册进度
- **账号列表** - 查看所有已注册账号
- **账号删除** - 批量删除账号
- **Token 导出** - 导出 OAuth Token
- **配置管理** - 修改配置文件

## 输出文件

- `registered_accounts.txt` - 注册账号（格式：邮箱----密码----邮箱密码----OAuth状态）
- `registered_accounts.csv` - CSV 格式账号
- `codex_tokens/` - OAuth Token JSON 文件

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web 界面 |
| `/api/config` | GET/POST | 获取/保存配置 |
| `/api/start` | POST | 启动注册任务 |
| `/api/stop` | POST | 停止注册任务 |
| `/api/status` | GET | 任务状态 |
| `/api/logs` | GET | SSE 日志流 |
| `/api/accounts` | GET/DELETE | 账号列表/删除 |
| `/api/export` | POST | 导出 Token |

## 注意事项

1. 请确保临时邮箱 API 密钥有效
2. 代理需要稳定，建议使用住宅代理
3. 注册过程请遵守 OpenAI 服务条款
4. 批量注册时注意控制频率，避免触发限制

## 端口

默认端口：`5000`

## 许可证

仅供学习和研究使用，请遵守相关服务条款。

---

**更新日期**：2026-03-19
