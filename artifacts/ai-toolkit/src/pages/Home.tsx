import { useState, useMemo } from "react";
import { tools, categories, Tool } from "@/data/tools";
import { ToolCard } from "@/components/ToolCard";
import { ToolDetail } from "@/components/ToolDetail";
import { StatsBar } from "@/components/StatsBar";
import { SearchBar } from "@/components/SearchBar";

export default function Home() {
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [filterWebUI, setFilterWebUI] = useState(false);

  const filtered = useMemo(() => {
    return tools.filter((t) => {
      const matchCat =
        selectedCategory === "all" || t.category === selectedCategory;
      const matchSearch =
        !searchQuery ||
        t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.tags.some((tag) =>
          tag.toLowerCase().includes(searchQuery.toLowerCase())
        );
      const matchWebUI = !filterWebUI || t.hasWebUI;
      return matchCat && matchSearch && matchWebUI;
    });
  }, [selectedCategory, searchQuery, filterWebUI]);

  return (
    <div className="min-h-screen bg-[#0d1117] text-gray-100">
      <header className="border-b border-[#21262d] bg-[#161b22] sticky top-0 z-40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center font-bold text-white text-sm shadow-lg">
              AI
            </div>
            <div>
              <h1 className="font-bold text-white text-lg leading-none">
                AI Account Toolkit
              </h1>
              <p className="text-xs text-gray-400 mt-0.5">
                AI 账号注册与管理工具集
              </p>
            </div>
          </div>
          <a
            href="https://github.com/adminlove520/AI-Account-Toolkit"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-sm text-gray-300 hover:text-white transition-all"
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
            </svg>
            GitHub
          </a>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-8">
        <StatsBar tools={tools} />

        <div className="mt-8 mb-6">
          <SearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            filterWebUI={filterWebUI}
            onFilterWebUI={setFilterWebUI}
            count={filtered.length}
          />
        </div>

        <div className="flex gap-6">
          <aside className="w-48 shrink-0">
            <nav className="space-y-1 sticky top-24">
              {categories.map((cat) => {
                const count =
                  cat.id === "all"
                    ? tools.length
                    : tools.filter((t) => t.category === cat.id).length;
                return (
                  <button
                    key={cat.id}
                    onClick={() => setSelectedCategory(cat.id)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between transition-all ${
                      selectedCategory === cat.id
                        ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                        : "text-gray-400 hover:text-gray-200 hover:bg-[#21262d]"
                    }`}
                  >
                    <span>{cat.label}</span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded-full ${
                        selectedCategory === cat.id
                          ? "bg-blue-500/30 text-blue-300"
                          : "bg-[#30363d] text-gray-500"
                      }`}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </nav>
          </aside>

          <main className="flex-1 min-w-0">
            {filtered.length === 0 ? (
              <div className="text-center py-20 text-gray-500">
                <div className="text-4xl mb-3">🔍</div>
                <p>没有找到匹配的工具</p>
                <button
                  onClick={() => {
                    setSearchQuery("");
                    setSelectedCategory("all");
                    setFilterWebUI(false);
                  }}
                  className="mt-3 text-blue-400 hover:text-blue-300 text-sm"
                >
                  清除筛选条件
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {filtered.map((tool) => (
                  <ToolCard
                    key={tool.id}
                    tool={tool}
                    onClick={() => setSelectedTool(tool)}
                  />
                ))}
              </div>
            )}
          </main>
        </div>
      </div>

      {selectedTool && (
        <ToolDetail tool={selectedTool} onClose={() => setSelectedTool(null)} />
      )}

      <footer className="mt-16 border-t border-[#21262d] bg-[#0d1117]">
        <div className="max-w-7xl mx-auto px-4 py-8 text-center text-gray-500 text-sm">
          <p>
            AI Account Toolkit &mdash; 开源项目，仅供学习研究使用
          </p>
          <p className="mt-2 text-xs text-gray-600">
            本工具集来自{" "}
            <a
              href="https://github.com/adminlove520/AI-Account-Toolkit"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 hover:text-blue-400"
            >
              github.com/adminlove520/AI-Account-Toolkit
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
