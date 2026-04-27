"use client";
import { adminFetch } from "@/lib/auth";

/**
 * HLKM 전문가 인증
 * - 검토 대기 큐 (field 별)
 * - 각 신청: field, organization, license_number, documentUrl
 * - 액션: [승인] (weight_multiplier 입력), [반려] (reason)
 * - 인증된 전문가 목록 (field 별 그룹)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import StatCard from "../_components/StatCard";

interface Credential {
  id: string;
  userId: string;
  field: string;
  organization: string | null;
  licenseNumber: string | null;
  documentUrl: string | null;
  note: string | null;
  verified?: boolean;
  weightMultiplier?: number | null;
  submittedAt: string;
  verifiedAt?: string | null;
  expiresAt?: string | null;
}

interface FieldsResponse {
  fields: string[];
}

const FIELD_LABEL: Record<string, string> = {
  law: "법률",
  medicine: "의학",
  finance: "금융",
  engineering: "공학",
  education: "교육",
  government: "공공/정부",
  research: "연구",
  journalism: "저널리즘",
};

export default function ExpertsPage() {
  const [pending, setPending] = useState<Credential[]>([]);
  const [verified, setVerified] = useState<Credential[]>([]);
  const [fields, setFields] = useState<string[]>([]);
  const [activeField, setActiveField] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [verifyTarget, setVerifyTarget] = useState<Credential | null>(null);
  const [weightMultiplier, setWeightMultiplier] = useState(1.5);
  const [rejectTarget, setRejectTarget] = useState<Credential | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const loadFields = useCallback(async () => {
    const resp = await adminFetch("/api/knowledge/expert/fields");
    if (resp.ok) {
      const data: FieldsResponse = await resp.json();
      setFields(data.fields);
      if (!activeField && data.fields.length > 0) setActiveField(data.fields[0]);
    }
  }, [activeField]);

  const loadPending = useCallback(async () => {
    const qs = new URLSearchParams();
    const resp = await adminFetch(`/api/knowledge/expert/pending?${qs}`);
    if (resp.ok) setPending(await resp.json());
    else setPending([]);
  }, []);

  const loadVerified = useCallback(async () => {
    if (!activeField) return;
    const resp = await adminFetch(`/api/knowledge/expert/by-field/${encodeURIComponent(activeField)}`);
    if (resp.ok) setVerified(await resp.json());
    else setVerified([]);
  }, [activeField]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadFields(), loadPending(), loadVerified()]);
    } finally {
      setLoading(false);
    }
  }, [loadFields, loadPending, loadVerified]);

  useEffect(() => {
    reload();
  }, [reload]);

  const submitVerify = async () => {
    if (!verifyTarget) return;
    setBusy(verifyTarget.id);
    try {
      const resp = await adminFetch(
        `/api/knowledge/expert/verify/${encodeURIComponent(verifyTarget.id)}`,
        {
          method: "POST",
          body: JSON.stringify({ weight_multiplier: weightMultiplier }),
        }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "전문가 자격 승인됨" });
      setVerifyTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const submitReject = async () => {
    if (!rejectTarget) return;
    if (!rejectReason.trim()) {
      setMessage({ ok: false, text: "사유를 입력하세요" });
      return;
    }
    setBusy(rejectTarget.id);
    try {
      const resp = await adminFetch(
        `/api/knowledge/expert/reject/${encodeURIComponent(rejectTarget.id)}`,
        {
          method: "POST",
          body: JSON.stringify({ reason: rejectReason }),
        }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "자격 반려 처리" });
      setRejectTarget(null);
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const revoke = async (credId: string) => {
    const reason = prompt("철회 사유?");
    if (!reason) return;
    setBusy(credId);
    try {
      const resp = await adminFetch(
        `/api/knowledge/expert/revoke/${encodeURIComponent(credId)}`,
        {
          method: "POST",
          body: JSON.stringify({ reason }),
        }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setMessage({ ok: true, text: "자격 철회 완료" });
      reload();
    } catch (e: any) {
      setMessage({ ok: false, text: e?.message || "실패" });
    } finally {
      setBusy(null);
    }
  };

  const pendingByField = useMemo(() => {
    const grouped: Record<string, Credential[]> = {};
    for (const c of pending) {
      const f = c.field || "기타";
      grouped[f] = grouped[f] || [];
      grouped[f].push(c);
    }
    return grouped;
  }, [pending]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">전문가 인증</h1>
          <p className="mt-1 text-sm text-gray-500">
            분야별 자격 신청 검토 · 승인된 전문가는 기여 시 가중치 multiplier 적용.
          </p>
        </div>
        <button
          onClick={reload}
          disabled={loading}
          className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-60"
          style={{ borderColor: "#e5e7eb" }}
        >
          새로고침
        </button>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="검토 대기" value={pending.length} accent="warning" />
        <StatCard label="지원 분야 수" value={fields.length} accent="primary" />
        <StatCard label="현재 분야 인증자" value={verified.length} accent="success" hint={activeField} />
        <StatCard
          label="대기 분야 수"
          value={Object.keys(pendingByField).length}
          accent="neutral"
        />
      </div>

      {message && (
        <div
          className="rounded-lg border p-3 text-sm"
          style={{
            borderColor: message.ok ? "#bbf7d0" : "#fecaca",
            background: message.ok ? "#f0fdf4" : "#fef2f2",
            color: message.ok ? "#166534" : "#991b1b",
          }}
        >
          {message.text}
        </div>
      )}

      {/* 검토 대기 큐 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "#e5e7eb" }}>
          <h2 className="font-semibold text-gray-900">검토 대기 큐</h2>
        </div>
        <div className="divide-y" style={{ borderColor: "#f3f4f6" }}>
          {pending.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400">
              대기 중인 신청 없음
            </div>
          )}
          {Object.entries(pendingByField).map(([field, creds]) => (
            <div key={field} className="p-4">
              <h3 className="mb-3 text-sm font-semibold text-gray-700">
                {FIELD_LABEL[field] || field}
                <span className="ml-2 text-xs text-gray-400">({creds.length})</span>
              </h3>
              <div className="space-y-2">
                {creds.map((c) => (
                  <div
                    key={c.id}
                    className="rounded-lg border p-3 text-sm"
                    style={{ borderColor: "#f3f4f6" }}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-mono text-gray-600">{c.userId.slice(0, 14)}</span>
                      <span className="text-gray-400">·</span>
                      <span className="text-gray-700">{c.organization || "기관 미기재"}</span>
                      {c.licenseNumber && (
                        <>
                          <span className="text-gray-400">·</span>
                          <span className="font-mono text-gray-700">면허 {c.licenseNumber}</span>
                        </>
                      )}
                      <span className="ml-auto text-gray-400">
                        {new Date(c.submittedAt).toLocaleDateString("ko-KR")}
                      </span>
                    </div>
                    {c.note && (
                      <p className="mt-2 text-xs text-gray-600">{c.note}</p>
                    )}
                    <div className="mt-3 flex items-center gap-2">
                      {c.documentUrl && (
                        <a
                          href={c.documentUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          증빙서류
                        </a>
                      )}
                      <div className="ml-auto flex gap-1">
                        <button
                          onClick={() => {
                            setVerifyTarget(c);
                            setWeightMultiplier(1.5);
                          }}
                          disabled={busy !== null}
                          className="rounded-lg bg-green-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-green-700 disabled:opacity-60"
                        >
                          승인
                        </button>
                        <button
                          onClick={() => {
                            setRejectTarget(c);
                            setRejectReason("");
                          }}
                          disabled={busy !== null}
                          className="rounded-lg border px-2.5 py-1 text-[11px] text-red-700 hover:bg-red-50 disabled:opacity-60"
                          style={{ borderColor: "#fecaca" }}
                        >
                          반려
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 분야별 인증 전문가 */}
      <section className="rounded-xl border bg-white" style={{ borderColor: "#e5e7eb" }}>
        <div
          className="flex items-center gap-3 border-b px-4 py-3"
          style={{ borderColor: "#e5e7eb" }}
        >
          <h2 className="font-semibold text-gray-900">인증된 전문가</h2>
          <select
            value={activeField}
            onChange={(e) => setActiveField(e.target.value)}
            className="ml-auto rounded-lg border px-2 py-1 text-xs"
            style={{ borderColor: "#e5e7eb" }}
          >
            {fields.map((f) => (
              <option key={f} value={f}>
                {FIELD_LABEL[f] || f}
              </option>
            ))}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-600" style={{ borderColor: "#e5e7eb" }}>
                <th className="px-4 py-2 text-left font-medium">사용자</th>
                <th className="px-4 py-2 text-left font-medium">소속</th>
                <th className="px-4 py-2 text-right font-medium">Multiplier</th>
                <th className="px-4 py-2 text-left font-medium">인증일</th>
                <th className="px-4 py-2 text-left font-medium">만료</th>
                <th className="px-4 py-2 text-right font-medium">액션</th>
              </tr>
            </thead>
            <tbody>
              {verified.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-gray-400">
                    인증된 전문가 없음
                  </td>
                </tr>
              )}
              {verified.map((v) => (
                <tr key={v.id} className="border-b hover:bg-gray-50" style={{ borderColor: "#f3f4f6" }}>
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{v.userId.slice(0, 14)}</td>
                  <td className="px-4 py-3 text-xs text-gray-700">{v.organization || "-"}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-indigo-600">
                    {(v.weightMultiplier ?? 1.0).toFixed(2)}×
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {v.verifiedAt ? new Date(v.verifiedAt).toLocaleDateString("ko-KR") : "-"}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {v.expiresAt ? new Date(v.expiresAt).toLocaleDateString("ko-KR") : "무기한"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => revoke(v.id)}
                      disabled={busy !== null}
                      className="rounded-lg border px-2.5 py-1 text-[11px] text-red-700 hover:bg-red-50 disabled:opacity-60"
                      style={{ borderColor: "#fecaca" }}
                    >
                      철회
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 승인 모달 */}
      {verifyTarget && (
        <ModalOverlay onClose={() => setVerifyTarget(null)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">전문가 자격 승인</h2>
            <p className="mt-1 text-xs text-gray-500">
              분야: {FIELD_LABEL[verifyTarget.field] || verifyTarget.field}
            </p>
            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-gray-700">
                Weight Multiplier ({weightMultiplier.toFixed(2)}×)
              </label>
              <input
                type="range"
                min={1.0}
                max={3.0}
                step={0.1}
                value={weightMultiplier}
                onChange={(e) => setWeightMultiplier(parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="mt-1 flex justify-between text-[10px] text-gray-500">
                <span>1.0× (표준)</span>
                <span>3.0× (최고)</span>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setVerifyTarget(null)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitVerify}
                disabled={busy !== null}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
              >
                승인
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* 반려 모달 */}
      {rejectTarget && (
        <ModalOverlay onClose={() => setRejectTarget(null)}>
          <div className="w-full max-w-md rounded-xl border bg-white p-6" style={{ borderColor: "#e5e7eb" }}>
            <h2 className="text-lg font-bold text-gray-900">자격 반려</h2>
            <div className="mt-4">
              <label className="mb-1 block text-xs font-semibold text-gray-700">사유</label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={3}
                placeholder="서류 불충분..."
                className="w-full rounded-lg border p-2 text-sm"
                style={{ borderColor: "#e5e7eb" }}
              />
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setRejectTarget(null)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
                style={{ borderColor: "#e5e7eb" }}
              >
                취소
              </button>
              <button
                onClick={submitReject}
                disabled={busy !== null}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                반려 처리
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

function ModalOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,23,42,0.5)" }}
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}
