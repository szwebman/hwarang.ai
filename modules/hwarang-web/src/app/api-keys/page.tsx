"use client";

import { useState } from "react";

interface ApiKey {
  id: string;
  name: string;
  keyPrefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  isActive: boolean;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([
    { id: "1", name: "Production", keyPrefix: "hk-prod-a1b2", createdAt: "2026-04-01", lastUsedAt: "2026-04-13", isActive: true },
    { id: "2", name: "Development", keyPrefix: "hk-dev-c3d4", createdAt: "2026-04-05", lastUsedAt: null, isActive: true },
  ]);
  const [newKeyName, setNewKeyName] = useState("");
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const handleCreateKey = () => {
    if (!newKeyName.trim()) return;

    // 실제로는 API 호출
    const fakeKey = `hk-${newKeyName.toLowerCase()}-${Math.random().toString(36).slice(2, 34)}`;
    setGeneratedKey(fakeKey);

    setKeys((prev) => [
      ...prev,
      {
        id: String(prev.length + 1),
        name: newKeyName,
        keyPrefix: fakeKey.slice(0, 15) + "...",
        createdAt: new Date().toISOString().split("T")[0],
        lastUsedAt: null,
        isActive: true,
      },
    ]);
    setNewKeyName("");
  };

  const handleDeleteKey = (id: string) => {
    if (confirm("이 API 키를 삭제하시겠습니까? 이 키를 사용하는 모든 애플리케이션이 동작하지 않게 됩니다.")) {
      setKeys((prev) => prev.filter((k) => k.id !== id));
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">API 키 관리</h1>
            <p className="text-sm mt-1" style={{ color: "var(--muted-foreground)" }}>
              API 키를 사용하여 Hwarang API에 접근할 수 있습니다
            </p>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="px-4 py-2 rounded-xl text-sm font-medium text-white"
            style={{ background: "var(--primary)" }}
          >
            + 새 키 생성
          </button>
        </div>

        {/* 키 생성 폼 */}
        {showCreate && (
          <div className="rounded-2xl border p-6 mb-6" style={{ borderColor: "var(--border)", background: "var(--muted)" }}>
            <h3 className="font-semibold mb-4">새 API 키 생성</h3>
            <div className="flex gap-3">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="키 이름 (예: Production, My App)"
                className="flex-1 px-4 py-2 rounded-xl border text-sm"
                style={{ borderColor: "var(--border)", background: "var(--background)" }}
              />
              <button
                onClick={handleCreateKey}
                disabled={!newKeyName.trim()}
                className="px-6 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50"
                style={{ background: "var(--primary)" }}
              >
                생성
              </button>
            </div>

            {/* 생성된 키 표시 (1회만) */}
            {generatedKey && (
              <div className="mt-4 p-4 rounded-xl border" style={{ borderColor: "var(--primary)", background: "var(--accent)" }}>
                <p className="text-sm font-semibold mb-2" style={{ color: "var(--primary)" }}>
                  API 키가 생성되었습니다. 이 키는 다시 볼 수 없으니 지금 복사하세요!
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 rounded-lg text-sm font-mono" style={{ background: "var(--background)" }}>
                    {generatedKey}
                  </code>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(generatedKey);
                    }}
                    className="px-3 py-2 rounded-lg text-sm border"
                    style={{ borderColor: "var(--border)" }}
                  >
                    복사
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 사용법 안내 */}
        <div className="rounded-2xl border p-5 mb-6" style={{ borderColor: "var(--border)" }}>
          <h3 className="text-sm font-semibold mb-3">빠른 시작</h3>
          <pre className="text-xs p-3 rounded-lg overflow-x-auto" style={{ background: "var(--muted)" }}>
{`curl https://api.hwarang.ai/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "hwarang-code-7b",
    "messages": [{"role": "user", "content": "안녕하세요"}]
  }'`}
          </pre>
        </div>

        {/* 키 목록 */}
        <div className="rounded-2xl border overflow-hidden" style={{ borderColor: "var(--border)" }}>
          <table className="w-full">
            <thead>
              <tr style={{ background: "var(--muted)" }}>
                <th className="text-left text-xs font-semibold px-5 py-3">이름</th>
                <th className="text-left text-xs font-semibold px-5 py-3">키</th>
                <th className="text-left text-xs font-semibold px-5 py-3">생성일</th>
                <th className="text-left text-xs font-semibold px-5 py-3">마지막 사용</th>
                <th className="text-left text-xs font-semibold px-5 py-3">상태</th>
                <th className="text-right text-xs font-semibold px-5 py-3">액션</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-5 py-4 text-sm font-medium">{key.name}</td>
                  <td className="px-5 py-4">
                    <code className="text-xs px-2 py-1 rounded" style={{ background: "var(--muted)" }}>
                      {key.keyPrefix}
                    </code>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--muted-foreground)" }}>{key.createdAt}</td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--muted-foreground)" }}>
                    {key.lastUsedAt || "사용 안 됨"}
                  </td>
                  <td className="px-5 py-4">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${key.isActive ? "" : "opacity-50"}`}
                      style={{ background: key.isActive ? "#dcfce7" : "var(--muted)", color: key.isActive ? "#166534" : "var(--muted-foreground)" }}>
                      {key.isActive ? "활성" : "비활성"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <button
                      onClick={() => handleDeleteKey(key.id)}
                      className="text-xs px-3 py-1 rounded-lg"
                      style={{ color: "var(--destructive)" }}
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
