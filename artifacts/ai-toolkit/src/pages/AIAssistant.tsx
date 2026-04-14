import { useState } from "react";

type AgentActionParameter = {
  name: string;
  type: string;
  description: string;
  required?: boolean;
  default?: unknown;
  enum?: unknown[];
};

type AgentAction = {
  name: string;
  label: string;
  description?: string;
  method: string;
  path: string;
  tab?: string;
  safety: "safe" | "requires-confirmation";
  parameters?: AgentActionParameter[];
  bodyHint?: Record<string, unknown>;
};

type AgentResponse = {
  success: boolean;
  sessionId: string;
  reply: string;
  skill: {
    id: string;
    title: string;
    tab: string;
    purpose: string;
  };
  registry?: {
    skillCount: number;
    toolCount: number;
  };
  actions: AgentAction[];
  nextSteps: string[];
  error?: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
};

const quickPrompts = [
  "我要注册 Cursor 账号，帮我定位需要准备什么",
  "Outlook 账号需要批量验证和清洗",
  "我要读取邮箱验证码",
  "帮我检测一批 Token 是否有效",
  "查看当前任务和代理池状态",
  "完整工作流开始前需要检查什么",
];

export default function AIAssistant({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "我是主功能任务中枢。输入你要做的事，我会把任务路由到 Cursor、Outlook、邮件、Token、数据、监控或完整工作流，并列出可用操作。",
    },
  ]);
  const [result, setResult] = useState<AgentResponse | null>(null);
  const [toolFeedback, setToolFeedback] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const runToolCheck = async (action: AgentAction, dryRun = false) => {
    if (!action.name) return;
    const params = action.bodyHint || {};
    setToolFeedback(prev => ({ ...prev, [action.name]: "处理中…" }));
    try {
      const response = await fetch(dryRun ? "/api/agent/execute" : "/api/agent/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dryRun ? { toolName: action.name, params, dryRun: true } : { toolName: action.name, params }),
      });
      const data = await response.json();
      const text = response.ok
        ? JSON.stringify(dryRun ? data.wouldCall || data.output || data : data.normalizedParams || data, null, 2)
        : JSON.stringify(data.issues || data.error || data, null, 2);
      setToolFeedback(prev => ({ ...prev, [action.name]: text }));
    } catch (err) {
      setToolFeedback(prev => ({ ...prev, [action.name]: err instanceof Error ? err.message : "请求失败" }));
    }
  };

  const submit = async (text = input) => {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: message }]);
    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, sessionId }),
      });
      const data = await response.json() as AgentResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "任务中枢返回失败");
      setSessionId(data.sessionId);
      setResult(data);
      setMessages(prev => [...prev, { role: "assistant", content: data.reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "请求失败";
      setError(msg);
      setMessages(prev => [...prev, { role: "assistant", content: `处理失败：${msg}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_380px] gap-5">
      <section className="bg-[#161b22] border border-[#21262d] rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-[#21262d] flex items-center justify-between gap-3">
          <div>
            <h2 className="text-white font-semibold">动态 Agent / Tool 中枢</h2>
            <p className="text-xs text-gray-500 mt-1">基于已注册 Skill 和 Tool 做参数校验、dry-run 与受控执行</p>
          </div>
          {sessionId && <span className="text-[10px] text-gray-500 font-mono">{sessionId.slice(0, 8)}</span>}
        </div>

        <div className="p-5 h-[520px] overflow-y-auto space-y-3">
          {messages.map((message, index) => (
            <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap leading-relaxed ${
                  message.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-[#0d1117] border border-[#30363d] text-gray-200"
                }`}
              >
                {message.content}
              </div>
            </div>
          ))}
          {busy && <div className="text-sm text-gray-500">正在分析主功能路由…</div>}
        </div>

        <div className="p-4 border-t border-[#21262d] space-y-3">
          <div className="flex gap-2 flex-wrap">
            {quickPrompts.map(prompt => (
              <button
                key={prompt}
                type="button"
                onClick={() => submit(prompt)}
                disabled={busy}
                className="text-xs px-3 py-1.5 rounded-full bg-[#21262d] hover:bg-[#30363d] text-gray-400 hover:text-gray-200 disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
          <form className="flex gap-2" onSubmit={event => { event.preventDefault(); submit(); }}>
            <input
              value={input}
              onChange={event => setInput(event.target.value)}
              placeholder="例如：我要批量注册 Cursor 并监控失败原因"
              className="flex-1 bg-[#0d1117] border border-[#30363d] rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="px-5 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold"
            >
              分析
            </button>
          </form>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
      </section>

      <aside className="space-y-4">
        <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-5">
          <div className="text-xs text-gray-500 mb-2">当前路由</div>
          {result ? (
            <div className="space-y-4">
              <div>
                <h3 className="text-white font-semibold">{result.skill.title}</h3>
                <p className="text-xs text-gray-400 leading-relaxed mt-2">{result.skill.purpose}</p>
                {result.registry && (
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-[#0d1117] rounded-lg border border-[#30363d] p-2">
                      <div className="text-gray-500">Skills</div>
                      <div className="text-white font-mono">{result.registry.skillCount}</div>
                    </div>
                    <div className="bg-[#0d1117] rounded-lg border border-[#30363d] p-2">
                      <div className="text-gray-500">Tools</div>
                      <div className="text-white font-mono">{result.registry.toolCount}</div>
                    </div>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => onNavigate(result.skill.tab)}
                className="w-full py-2.5 rounded-xl bg-emerald-600/80 hover:bg-emerald-600 text-white text-sm font-medium"
              >
                打开对应功能页
              </button>
            </div>
          ) : (
            <p className="text-sm text-gray-500">输入任务后会显示建议进入的主功能页面。</p>
          )}
        </div>

        <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-5">
          <div className="text-xs text-gray-500 mb-3">可用动作</div>
          {result?.actions?.length ? (
            <div className="space-y-2">
              {result.actions.map(action => (
                <div key={action.name || `${action.method}-${action.path}-${action.label}`} className="bg-[#0d1117] border border-[#30363d] rounded-xl p-3">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-sm text-gray-200">{action.label}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${action.safety === "safe" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"}`}>
                      {action.safety === "safe" ? "可查看" : "需确认"}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-gray-500 break-all">{action.name ? `${action.name} · ` : ""}{action.method} {action.path}</div>
                  {action.description && <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">{action.description}</p>}
                  {!!action.parameters?.length && (
                    <div className="mt-2 space-y-1">
                      {action.parameters.map(param => (
                        <div key={param.name} className="flex items-center justify-between gap-2 text-[11px] bg-[#161b22] rounded-lg px-2 py-1">
                          <span className="text-gray-300 font-mono">{param.name}</span>
                          <span className="text-gray-500">{param.type}{param.required ? " · 必填" : ""}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex gap-2">
                    <button type="button" onClick={() => runToolCheck(action)} className="flex-1 text-xs rounded-lg bg-[#21262d] hover:bg-[#30363d] text-gray-300 py-1.5">校验参数</button>
                    <button type="button" onClick={() => runToolCheck(action, true)} className="flex-1 text-xs rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 py-1.5">dry-run</button>
                  </div>
                  {toolFeedback[action.name] && (
                    <pre className="mt-2 text-[10px] text-gray-500 bg-[#161b22] rounded-lg p-2 overflow-x-auto whitespace-pre-wrap">
                      {toolFeedback[action.name]}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">还没有动作建议。</p>
          )}
        </div>

        <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-5">
          <div className="text-xs text-gray-500 mb-3">下一步</div>
          {result?.nextSteps?.length ? (
            <ol className="space-y-2 text-sm text-gray-300 list-decimal list-inside">
              {result.nextSteps.map(step => <li key={step}>{step}</li>)}
            </ol>
          ) : (
            <p className="text-sm text-gray-500">任务分析后会给出执行顺序。</p>
          )}
        </div>
      </aside>
    </div>
  );
}
