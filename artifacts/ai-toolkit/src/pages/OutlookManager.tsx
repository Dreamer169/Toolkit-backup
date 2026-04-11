import { useState, useRef } from "react";

interface MailMsg { id: string; subject: string; from: string; fromName: string; receivedAt: string; preview: string; isRead: boolean; }
interface Profile { displayName?: string; mail?: string; userPrincipalName?: string; }
type Step = 1 | 2 | 3 | 4;

const STEPS = [
  { n: 1, label: "创建临时邮箱",        icon: "📬" },
  { n: 2, label: "注册 Outlook 账号",   icon: "📝" },
  { n: 3, label: "获取 OAuth2 Token",   icon: "🔑" },
  { n: 4, label: "读取收件箱",          icon: "📥" },
];

export default function OutlookManager() {
  const [step, setStep]               = useState<Step>(1);
  const [copied, setCopied]           = useState<string | null>(null);

  // Step 1 – 临时邮箱
  const [tmpEmail, setTmpEmail]       = useState("");
  const [tmpPass,  setTmpPass]        = useState("");
  const [tmpToken, setTmpToken]       = useState("");
  const [tmpDomains, setTmpDomains]   = useState<string[]>([]);
  const [tmpDomain, setTmpDomain]     = useState("");
  const [step1Busy, setStep1Busy]     = useState(false);
  const [step1Msgs, setStep1Msgs]     = useState<Array<{ from: string; subject: string; intro: string }>>([]);
  const pollRef = useRef<ReturnType<typeof setInterval>|null>(null);

  // Step 3 – OAuth2
  const [clientId,  setClientId]      = useState("9e5f94bc-e8a4-4e73-b8be-63364c29d753"); // 常用公共 client_id
  const [refreshTok, setRefreshTok]   = useState("");
  const [tenantId,  setTenantId]      = useState("common");
  const [accessTok, setAccessTok]     = useState("");
  const [oauthBusy, setOauthBusy]     = useState(false);
  const [oauthErr,  setOauthErr]      = useState("");
  const [profile,   setProfile]       = useState<Profile|null>(null);

  // Step 4 – 邮件
  const [messages,  setMessages]      = useState<MailMsg[]>([]);
  const [msgBusy,   setMsgBusy]       = useState(false);
  const [msgErr,    setMsgErr]        = useState("");
  const [folder,    setFolder]        = useState("inbox");
  const [search,    setSearch]        = useState("");
  const [selMsg,    setSelMsg]        = useState<string|null>(null);

  const copy = (text: string, k: string) => {
    navigator.clipboard.writeText(text);
    setCopied(k);
    setTimeout(() => setCopied(null), 1200);
  };

  // ── Step 1: 创建临时邮箱 ──────────────────────────────
  const loadDomains = async () => {
    if (tmpDomains.length) return;
    const r = await fetch("/api/tools/email/domains");
    const d = await r.json();
    if (d.domains?.length) { setTmpDomains(d.domains); setTmpDomain(d.domains[0]); }
  };

  const createTmpEmail = async () => {
    setStep1Busy(true);
    const user = Math.random().toString(36).slice(2, 12) + Math.floor(Math.random() * 999);
    const pass = Math.random().toString(36).slice(2, 14);
    const address = `${user}@${tmpDomain}`;
    try {
      const r = await fetch("/api/tools/email/create", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, password: pass }),
      });
      const d = await r.json();
      if (d.success) {
        setTmpEmail(address); setTmpPass(pass); setTmpToken(d.token ?? "");
        startPollMailTM(d.token ?? "");
      }
    } catch {}
    setStep1Busy(false);
  };

  const startPollMailTM = (tok: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch("/api/tools/email/messages", { headers: { "x-mail-token": tok } });
        const d = await r.json();
        if (d.success) setStep1Msgs(d.messages ?? []);
      } catch {}
    }, 5000);
  };

  // ── Step 3: OAuth2 刷新 ──────────────────────────────
  const doRefresh = async () => {
    setOauthBusy(true); setOauthErr(""); setProfile(null);
    try {
      const r = await fetch("/api/tools/outlook/refresh-token", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, refreshToken: refreshTok, tenantId }),
      });
      const d = await r.json();
      if (d.success) {
        setAccessTok(d.accessToken);
        if (d.refreshToken) setRefreshTok(d.refreshToken);
        const pr = await fetch("/api/tools/outlook/profile", { headers: { "x-access-token": d.accessToken } });
        const pd = await pr.json();
        if (pd.success) setProfile(pd.profile);
      } else { setOauthErr(d.error ?? "OAuth2 失败"); }
    } catch (e) { setOauthErr(String(e)); }
    setOauthBusy(false);
  };

  // ── Step 4: 读取邮件 ──────────────────────────────────
  const fetchMessages = async () => {
    if (!accessTok) return;
    setMsgBusy(true); setMsgErr("");
    try {
      const r = await fetch("/api/tools/outlook/messages", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessToken: accessTok, folder, top: 30, search: search || undefined }),
      });
      const d = await r.json();
      if (d.success) setMessages(d.messages);
      else setMsgErr(d.error ?? "获取失败");
    } catch (e) { setMsgErr(String(e)); }
    setMsgBusy(false);
  };

  const extractCode = (text: string) => text?.match(/\b(\d{6})\b/)?.[1] ?? text?.match(/\b([A-Z0-9]{8,})\b/)?.[1] ?? null;

  const Pill = ({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) => (
    <button onClick={onClick} className={`px-3 py-1 rounded-full text-xs border transition-all ${active ? "bg-blue-600 text-white border-blue-500" : "bg-[#21262d] border-[#30363d] text-gray-400 hover:text-white"}`}>{children}</button>
  );

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-white mb-1">Outlook 邮箱管理工作流</h2>
        <p className="text-sm text-gray-400">
          参考 <span className="text-blue-400">outlook-batch-manager</span> 设计，整合 MailTM 临时邮箱注册 → 微软 OAuth2 取件的完整流程
        </p>
      </div>

      {/* 步骤导航 */}
      <div className="flex items-center gap-0">
        {STEPS.map((s, i) => (
          <div key={s.n} className="flex items-center flex-1">
            <button
              onClick={() => { setStep(s.n as Step); if (s.n === 1) loadDomains(); }}
              className={`flex flex-col items-center gap-1 flex-1 py-3 px-2 rounded-xl border transition-all ${
                step === s.n ? "bg-blue-500/10 border-blue-500/40 text-white" : "bg-[#161b22] border-[#21262d] text-gray-500 hover:text-gray-300"
              }`}
            >
              <span className="text-lg">{s.icon}</span>
              <span className="text-[11px] font-medium text-center leading-tight">{s.label}</span>
              <span className={`text-[10px] w-4 h-4 rounded-full flex items-center justify-center font-bold ${step === s.n ? "bg-blue-500 text-white" : "bg-[#30363d] text-gray-500"}`}>{s.n}</span>
            </button>
            {i < STEPS.length - 1 && <div className="w-4 h-px bg-[#30363d] shrink-0" />}
          </div>
        ))}
      </div>

      {/* ── Step 1: 临时邮箱 ── */}
      {step === 1 && (
        <div className="space-y-4">
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-gray-300">创建 MailTM 临时邮箱</h3>
            <div className="flex gap-3">
              <select value={tmpDomain} onChange={(e) => setTmpDomain(e.target.value)} onClick={loadDomains}
                className="flex-1 bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-blue-500">
                {tmpDomains.length === 0 ? <option>加载域名中...</option> : tmpDomains.map((d) => <option key={d}>{d}</option>)}
              </select>
              <button onClick={createTmpEmail} disabled={step1Busy || !tmpDomain}
                className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-all">
                {step1Busy ? "创建中..." : "创建邮箱"}
              </button>
            </div>
            {tmpEmail && (
              <div className="space-y-2">
                {[
                  { label: "邮箱地址", value: tmpEmail, k: "te" },
                  { label: "密码",     value: tmpPass,  k: "tp" },
                  { label: "Token",    value: tmpToken, k: "tt" },
                ].map(({ label, value, k }) => (
                  <div key={k} className="flex items-center gap-3 bg-[#0d1117] rounded-lg px-3 py-2">
                    <span className="text-xs text-gray-500 w-16 shrink-0">{label}</span>
                    <span className="text-xs font-mono text-emerald-300 flex-1 truncate">{value}</span>
                    <button onClick={() => copy(value, k)} className={`text-xs px-2 py-0.5 rounded border shrink-0 transition-all ${copied === k ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400" : "bg-[#21262d] border-[#30363d] text-gray-500 hover:text-white"}`}>
                      {copied === k ? "✓" : "复制"}
                    </button>
                  </div>
                ))}
                <div className="flex items-center gap-2 pt-1">
                  <span className="flex items-center gap-1 text-xs text-emerald-400"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />实时监听中</span>
                  <span className="text-xs text-gray-500">每 5 秒刷新 · {step1Msgs.length} 封</span>
                </div>
                {step1Msgs.length > 0 && (
                  <div className="space-y-2 max-h-40 overflow-y-auto">
                    {step1Msgs.map((m, i) => {
                      const code = extractCode(m.intro || m.subject);
                      return (
                        <div key={i} className="bg-[#161b22] rounded-lg px-3 py-2 flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-gray-200 truncate">{m.subject}</p>
                            <p className="text-[11px] text-gray-500">{m.from?.address ?? m.from}</p>
                          </div>
                          {code && <button onClick={() => copy(code, `vc-${i}`)} className={`text-xs px-2 py-0.5 rounded border font-mono font-bold ${copied === `vc-${i}` ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400" : "bg-yellow-500/10 border-yellow-500/30 text-yellow-400"}`}>{copied === `vc-${i}` ? "已复制" : `验证码: ${code}`}</button>}
                        </div>
                      );
                    })}
                  </div>
                )}
                <button onClick={() => setStep(2)}
                  className="w-full py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white text-sm font-medium transition-all">
                  用此邮箱注册 Outlook → 下一步
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Step 2: 注册指引 ── */}
      {step === 2 && (
        <div className="space-y-4">
          {tmpEmail && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 flex items-center gap-3">
              <span className="text-xl">📬</span>
              <div>
                <p className="text-xs text-gray-400">使用以下邮箱进行 Outlook 注册</p>
                <p className="text-sm font-mono font-bold text-blue-300">{tmpEmail}</p>
              </div>
              <button onClick={() => copy(tmpEmail, "reg-email")} className="ml-auto text-xs px-2 py-1 rounded border border-[#30363d] bg-[#21262d] text-gray-400 hover:text-white">{copied === "reg-email" ? "✓" : "复制"}</button>
            </div>
          )}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-gray-300">Outlook/Hotmail 注册步骤</h3>
            <ol className="space-y-3">
              {[
                { n: "1", title: "打开注册页", desc: '访问 outlook.com，点击【创建免费帐户】', action: { label: "打开 Outlook 注册", url: "https://signup.live.com/signup" } },
                { n: "2", title: "填写手机/邮箱", desc: `选择【使用当前电子邮件地址】，输入上方 MailTM 邮箱：${tmpEmail || "（请先在第一步创建）"}` },
                { n: "3", title: "接收验证码", desc: "Microsoft 会向 MailTM 邮箱发送验证码，回到第一步查看实时收件箱" },
                { n: "4", title: "完成注册", desc: "填写姓名、生日，通过验证码验证完成注册，记录你的 @outlook.com 邮箱地址和密码" },
                { n: "5", title: "获取 OAuth2 Token", desc: "注册完成后，前往第三步用工具获取 Refresh Token，用于后续 API 取件" },
              ].map((item) => (
                <li key={item.n} className="flex gap-3">
                  <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold shrink-0 mt-0.5">{item.n}</span>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-200">{item.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{item.desc}</p>
                    {item.action && (
                      <a href={item.action.url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-1.5 text-xs px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition-all">
                        {item.action.label} →
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-3">
              <p className="text-xs font-semibold text-yellow-400 mb-1">关于 Outlook 批量自动化注册</p>
              <p className="text-xs text-gray-400">完整自动化注册需要 Playwright/patchright 浏览器自动化环境（参考 <a href="https://github.com/hrhcode/outlook-batch-manager" target="_blank" className="text-blue-400">outlook-batch-manager</a>）。本工具提供工作流接口，自动化执行需在本地部署含浏览器的 Python 环境。</p>
            </div>
            <button onClick={() => setStep(3)} className="w-full py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-sm font-medium">注册完成 → 获取 OAuth2 Token</button>
          </div>
        </div>
      )}

      {/* ── Step 3: OAuth2 ── */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-gray-300">微软 OAuth2 刷新 Token</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Client ID <span className="text-gray-600">（预填公共ID）</span></label>
                <input value={clientId} onChange={(e) => setClientId(e.target.value)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-xs font-mono text-gray-300 focus:outline-none focus:border-blue-500" />
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Tenant ID <span className="text-gray-600">（默认 common）</span></label>
                <input value={tenantId} onChange={(e) => setTenantId(e.target.value)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-xs font-mono text-gray-300 focus:outline-none focus:border-blue-500" />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Refresh Token</label>
              <textarea value={refreshTok} onChange={(e) => setRefreshTok(e.target.value)} rows={3}
                placeholder="粘贴从 Microsoft 授权流程获取的 Refresh Token..."
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-xs font-mono text-gray-300 focus:outline-none focus:border-blue-500 resize-none" />
            </div>
            <button onClick={doRefresh} disabled={oauthBusy || !refreshTok || !clientId}
              className="w-full py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg text-white text-sm font-medium transition-all">
              {oauthBusy ? "刷新中..." : "🔑 刷新 Access Token"}
            </button>
            {oauthErr && <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{oauthErr}</p>}
            {accessTok && (
              <div className="space-y-3">
                {profile && (
                  <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 flex items-center gap-3">
                    <span className="text-xl">✅</span>
                    <div>
                      <p className="text-sm font-medium text-emerald-300">{profile.displayName}</p>
                      <p className="text-xs text-gray-400">{profile.mail ?? profile.userPrincipalName}</p>
                    </div>
                  </div>
                )}
                {[
                  { label: "Access Token (前80字符)", value: accessTok.slice(0, 80) + "...", full: accessTok, k: "at" },
                  { label: "Refresh Token (更新后)", value: refreshTok.slice(0, 60) + "...", full: refreshTok, k: "rt" },
                ].map(({ label, value, full, k }) => (
                  <div key={k} className="bg-[#0d1117] rounded-lg px-3 py-2 flex items-center gap-3">
                    <span className="text-xs text-gray-500 w-36 shrink-0">{label}</span>
                    <span className="text-xs font-mono text-blue-300 flex-1 truncate">{value}</span>
                    <button onClick={() => copy(full, k)} className={`text-xs px-2 py-0.5 rounded border shrink-0 ${copied === k ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400" : "bg-[#21262d] border-[#30363d] text-gray-500 hover:text-white"}`}>
                      {copied === k ? "✓" : "复制"}
                    </button>
                  </div>
                ))}
                <button onClick={() => setStep(4)} className="w-full py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-white text-sm font-medium">读取收件箱 → 下一步</button>
              </div>
            )}
          </div>

          <div className="bg-[#0d1117] border border-[#30363d] rounded-xl p-4">
            <p className="text-xs font-semibold text-gray-400 mb-2">如何获取 Refresh Token</p>
            <ol className="space-y-1 text-xs text-gray-500">
              <li>1. 访问 <a href="https://developer.microsoft.com/en-us/graph/graph-explorer" target="_blank" className="text-blue-400">Graph Explorer</a>，登录你的 Outlook 账号</li>
              <li>2. 点击"Consent to permissions"授权 Mail.Read 权限</li>
              <li>3. 在浏览器开发者工具 Network 选项卡中，找到对 <code className="text-gray-300">/token</code> 的请求，获取 refresh_token</li>
              <li>4. 或使用 <a href="https://github.com/hrhcode/outlook-batch-manager" target="_blank" className="text-blue-400">outlook-batch-manager</a> 的 OAuth2 授权页面自动获取</li>
            </ol>
          </div>
        </div>
      )}

      {/* ── Step 4: 收件箱 ── */}
      {step === 4 && (
        <div className="space-y-4">
          {!accessTok && (
            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 text-center">
              <p className="text-sm text-yellow-400">请先在第三步获取 Access Token</p>
              <button onClick={() => setStep(3)} className="mt-2 text-xs px-4 py-1.5 bg-yellow-500/20 border border-yellow-500/30 rounded-lg text-yellow-400">← 返回第三步</button>
            </div>
          )}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 space-y-4">
            {profile && (
              <div className="flex items-center gap-2 pb-3 border-b border-[#21262d]">
                <span className="text-base">📧</span>
                <span className="text-sm font-medium text-white">{profile.mail ?? profile.userPrincipalName}</span>
                <span className="text-xs text-gray-500 ml-auto">Microsoft Graph API</span>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {["inbox","sentItems","drafts","junkemail","deleteditems"].map((f) => (
                <Pill key={f} active={folder === f} onClick={() => setFolder(f)}>
                  {f === "inbox" ? "收件箱" : f === "sentItems" ? "已发送" : f === "drafts" ? "草稿箱" : f === "junkemail" ? "垃圾邮件" : "已删除"}
                </Pill>
              ))}
            </div>
            <div className="flex gap-2">
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索关键词（可选）"
                className="flex-1 bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-xs text-gray-300 focus:outline-none focus:border-blue-500" />
              <button onClick={fetchMessages} disabled={msgBusy || !accessTok}
                className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-white text-xs font-medium transition-all">
                {msgBusy ? "加载中..." : "获取邮件"}
              </button>
            </div>
            {msgErr && <p className="text-xs text-red-400">{msgErr}</p>}
            {messages.length > 0 && (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {messages.map((m) => {
                  const code = extractCode(m.preview || m.subject);
                  const time = new Date(m.receivedAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
                  return (
                    <div key={m.id} onClick={() => setSelMsg(selMsg === m.id ? null : m.id)}
                      className={`bg-[#0d1117] rounded-lg px-3 py-2.5 cursor-pointer hover:border-blue-500/30 border transition-all ${selMsg === m.id ? "border-blue-500/30" : "border-[#21262d]"}`}>
                      <div className="flex items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            {!m.isRead && <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />}
                            <p className="text-xs font-medium text-gray-200 truncate">{m.subject}</p>
                          </div>
                          <p className="text-[11px] text-gray-500 mt-0.5">{m.fromName || m.from} · {time}</p>
                        </div>
                        {code && (
                          <button onClick={(e) => { e.stopPropagation(); copy(code, `m-${m.id}`); }}
                            className={`text-[11px] px-2 py-0.5 rounded border font-mono font-bold shrink-0 ${copied === `m-${m.id}` ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400" : "bg-yellow-500/10 border-yellow-500/30 text-yellow-400"}`}>
                            {copied === `m-${m.id}` ? "已复制" : `验证码: ${code}`}
                          </button>
                        )}
                      </div>
                      {selMsg === m.id && (
                        <p className="mt-2 pt-2 border-t border-[#21262d] text-[11px] text-gray-400 leading-relaxed">{m.preview}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
