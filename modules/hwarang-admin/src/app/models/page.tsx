"use client";

import { useEffect, useState } from "react";

interface VLLMModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
  max_model_len?: number;
}

interface ModelConfig {
  defaultModel: string;    // 현재 기본 모델
  availableModels: VLLMModel[];
}

export default function ModelsPage() {
  const [config, setConfig] = useState<ModelConfig>({
    defaultModel: "",
    availableModels: [],
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testLoading, setTestLoading] = useState(false);

  useEffect(() => {
    fetchModels();
    const interval = setInterval(fetchModels, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchModels = async () => {
    try {
      // 1. vLLM에서 모델 목록
      const resp = await fetch("/api/models");
      if (resp.ok) {
        const data = await resp.json();
        setConfig(data);
      }
    } catch {}
    setLoading(false);
  };

  const handleSetDefault = async (modelId: string) => {
    setSaving(true);
    try {
      await fetch("/api/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ defaultModel: modelId }),
      });
      setConfig((prev) => ({ ...prev, defaultModel: modelId }));
    } catch {}
    setSaving(false);
  };

  const handleTestModel = async (modelId: string) => {
    setTestLoading(true);
    setTestResult(null);
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: modelId,
          messages: [{ role: "user", content: "안녕하세요, 간단히 자기소개 해주세요." }],
          max_tokens: 100,
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        const content = data.choices?.[0]?.message?.content || "응답 없음";
        const tokens = data.usage?.total_tokens || 0;
        setTestResult(`✅ 응답 (${tokens} 토큰): ${content}`);
      } else {
        setTestResult(`❌ 오류: ${resp.status}`);
      }
    } catch (e: any) {
      setTestResult(`❌ 연결 실패: ${e.message}`);
    }
    setTestLoading(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--muted)" }}>
        <div className="animate-pulse">모델 정보 로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--muted)" }}>
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">모델 관리</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            vLLM 서버의 모델을 관리하고, 기본 모델을 선택합니다
          </p>
        </div>

        {/* 현재 기본 모델 */}
        <div className="rounded-2xl p-5 mb-6" style={{ background: "var(--background)", border: "2px solid var(--primary)" }}>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xl">⭐</span>
            <h2 className="font-semibold">현재 기본 모델</h2>
          </div>
          {config.defaultModel ? (
            <div>
              <code className="text-sm px-3 py-1.5 rounded-lg" style={{ background: "var(--muted)" }}>
                {config.defaultModel}
              </code>
              <p className="text-xs mt-2" style={{ color: "var(--muted-foreground)" }}>
                모든 사용자의 채팅이 이 모델로 처리됩니다
              </p>
            </div>
          ) : (
            <p className="text-sm" style={{ color: "var(--destructive)" }}>
              기본 모델이 설정되지 않았습니다. 아래에서 모델을 선택하세요.
            </p>
          )}
        </div>

        {/* 사용 가능한 모델 목록 */}
        <div className="mb-6">
          <h2 className="font-semibold mb-3">사용 가능한 모델 ({config.availableModels.length}개)</h2>

          {config.availableModels.length === 0 ? (
            <div className="rounded-2xl p-8 text-center" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
              <p className="text-lg mb-2">🔴 vLLM 서버에 연결할 수 없습니다</p>
              <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
                vLLM 서버가 실행 중인지 확인하세요
              </p>
              <pre className="mt-4 text-xs p-3 rounded-lg text-left" style={{ background: "var(--muted)" }}>
{`poetry run python -m vllm.entrypoints.openai.api_server \\
  --model /mnt/nvme2/hwarang/models/qwen2.5-32b-int4 \\
  --trust-remote-code --gpu-memory-utilization 0.9 \\
  --max-model-len 2048 --port 8000`}
              </pre>
            </div>
          ) : (
            <div className="space-y-3">
              {config.availableModels.map((model) => {
                const isDefault = model.id === config.defaultModel;
                const shortName = model.id.split("/").pop() || model.id;

                return (
                  <div key={model.id}
                    className="rounded-2xl p-5 transition-all"
                    style={{
                      background: "var(--background)",
                      border: `2px solid ${isDefault ? "var(--primary)" : "var(--border)"}`,
                    }}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">{isDefault ? "⭐" : "🧠"}</span>
                        <div>
                          <div className="font-semibold flex items-center gap-2">
                            {shortName}
                            {isDefault && (
                              <span className="text-xs px-2 py-0.5 rounded-full text-white" style={{ background: "var(--primary)" }}>
                                기본 모델
                              </span>
                            )}
                          </div>
                          <div className="text-xs font-mono mt-0.5" style={{ color: "var(--muted-foreground)" }}>
                            {model.id}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "#dcfce7", color: "#166534" }}>
                          🟢 실행중
                        </span>
                      </div>
                    </div>

                    {/* 모델 상세 */}
                    <div className="grid grid-cols-3 gap-4 mt-4 text-sm">
                      <div>
                        <span style={{ color: "var(--muted-foreground)" }}>Owner: </span>
                        <span className="font-medium">{model.owned_by}</span>
                      </div>
                      <div>
                        <span style={{ color: "var(--muted-foreground)" }}>생성: </span>
                        <span className="font-medium">{new Date(model.created * 1000).toLocaleDateString("ko-KR")}</span>
                      </div>
                      <div>
                        <span style={{ color: "var(--muted-foreground)" }}>상태: </span>
                        <span className="font-medium" style={{ color: "#22c55e" }}>서빙 중</span>
                      </div>
                    </div>

                    {/* 액션 버튼 */}
                    <div className="flex gap-2 mt-4">
                      {!isDefault && (
                        <button
                          onClick={() => handleSetDefault(model.id)}
                          disabled={saving}
                          className="text-xs px-4 py-2 rounded-lg text-white font-medium disabled:opacity-50"
                          style={{ background: "var(--primary)" }}
                        >
                          {saving ? "설정 중..." : "⭐ 기본 모델로 설정"}
                        </button>
                      )}
                      <button
                        onClick={() => handleTestModel(model.id)}
                        disabled={testLoading}
                        className="text-xs px-4 py-2 rounded-lg border font-medium disabled:opacity-50"
                        style={{ borderColor: "var(--border)" }}
                      >
                        {testLoading ? "테스트 중..." : "🧪 추론 테스트"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 테스트 결과 */}
        {testResult && (
          <div className="rounded-2xl p-4 mb-6" style={{
            background: testResult.startsWith("✅") ? "#f0fdf4" : "#fef2f2",
            border: `1px solid ${testResult.startsWith("✅") ? "#bbf7d0" : "#fecaca"}`,
          }}>
            <p className="text-sm whitespace-pre-wrap">{testResult}</p>
          </div>
        )}

        {/* LoRA 어댑터 */}
        <div className="mb-6">
          <h2 className="font-semibold mb-3">LoRA 어댑터</h2>
          <div className="rounded-2xl p-5" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              학습된 LoRA 어댑터가 여기에 표시됩니다.
            </p>
            <p className="text-xs mt-2 font-mono" style={{ color: "var(--muted-foreground)" }}>
              경로: /mnt/nvme2/hwarang/lora_adapters/
            </p>
          </div>
        </div>

        {/* 설정 가이드 */}
        <div className="rounded-2xl p-5" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
          <h2 className="font-semibold mb-3">모델 추가 방법</h2>
          <div className="text-sm space-y-3" style={{ color: "var(--muted-foreground)" }}>
            <div>
              <strong>1. 새 모델 다운로드:</strong>
              <pre className="mt-1 text-xs p-2 rounded-lg" style={{ background: "var(--muted)" }}>
                hf download Qwen/Qwen2.5-14B-Instruct --local-dir /mnt/nvme2/hwarang/models/qwen2.5-14b
              </pre>
            </div>
            <div>
              <strong>2. vLLM 서버 재시작 (새 모델로):</strong>
              <pre className="mt-1 text-xs p-2 rounded-lg" style={{ background: "var(--muted)" }}>
{`poetry run python -m vllm.entrypoints.openai.api_server \\
  --model /mnt/nvme2/hwarang/models/새모델경로 \\
  --trust-remote-code --port 8000`}
              </pre>
            </div>
            <div>
              <strong>3. 이 페이지에서 "기본 모델로 설정" 클릭</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
