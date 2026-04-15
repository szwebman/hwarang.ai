"use client";

import { useEffect, useState } from "react";

/**
 * 롤(역할) 관리 페이지
 *
 * - 역할별 권한 매트릭스 표시/수정
 * - DB의 SystemSetting 테이블에 JSON으로 저장
 * - SUPER_ADMIN만 수정 가능, ADMIN은 조회만
 */

interface RolePermissions {
  [role: string]: {
    label: string;
    color: string;
    permissions: Record<string, boolean>;
  };
}

// 권한 카테고리와 항목
const PERMISSION_GROUPS: { group: string; items: { key: string; label: string; desc: string }[] }[] = [
  {
    group: "대시보드",
    items: [
      { key: "dashboard.view", label: "대시보드 조회", desc: "메인 대시보드 통계 확인" },
    ],
  },
  {
    group: "유저 관리",
    items: [
      { key: "users.view", label: "유저 목록 조회", desc: "전체 유저 리스트 열람" },
      { key: "users.edit", label: "유저 정보 수정", desc: "유저 상태, 플랜 변경" },
      { key: "users.delete", label: "유저 삭제", desc: "유저 계정 삭제" },
      { key: "users.token_adjust", label: "토큰 수동 조정", desc: "유저 토큰 잔액 직접 변경" },
    ],
  },
  {
    group: "플랜 관리",
    items: [
      { key: "plans.view", label: "플랜 조회", desc: "구독 상품 목록 확인" },
      { key: "plans.edit", label: "플랜 수정", desc: "가격, 토큰 수, 기능 변경" },
      { key: "plans.create", label: "플랜 생성", desc: "새로운 구독 상품 추가" },
      { key: "plans.delete", label: "플랜 삭제", desc: "구독 상품 제거" },
    ],
  },
  {
    group: "모델 관리",
    items: [
      { key: "models.view", label: "모델 조회", desc: "LLM 모델 상태 확인" },
      { key: "models.manage", label: "모델 로드/언로드", desc: "모델 시작/중지" },
    ],
  },
  {
    group: "서버 모니터링",
    items: [
      { key: "servers.view", label: "서버 상태 조회", desc: "GPU, CPU, 메모리 모니터링" },
    ],
  },
  {
    group: "매출/결제",
    items: [
      { key: "billing.view", label: "매출 현황 조회", desc: "결제 내역, 매출 통계" },
      { key: "billing.refund", label: "환불 처리", desc: "결제 환불 실행" },
    ],
  },
  {
    group: "관리자 관리",
    items: [
      { key: "admins.view", label: "관리자 목록 조회", desc: "관리자 계정 열람" },
      { key: "admins.create", label: "관리자 추가", desc: "새 관리자 계정 생성" },
      { key: "admins.edit", label: "관리자 수정", desc: "역할 변경, 비밀번호 초기화" },
      { key: "admins.delete", label: "관리자 제거", desc: "관리자 권한 삭제" },
    ],
  },
  {
    group: "시스템 설정",
    items: [
      { key: "system.settings", label: "시스템 설정", desc: "유지보수 모드, 전역 설정" },
      { key: "system.roles", label: "롤 권한 관리", desc: "역할별 권한 매트릭스 수정" },
      { key: "system.logs", label: "요청 로그 조회", desc: "API 요청 로그 열람" },
    ],
  },
];

const DEFAULT_PERMISSIONS: RolePermissions = {
  SUPER_ADMIN: {
    label: "최고 관리자",
    color: "#7c3aed",
    permissions: Object.fromEntries(
      PERMISSION_GROUPS.flatMap((g) => g.items.map((i) => [i.key, true]))
    ),
  },
  ADMIN: {
    label: "관리자",
    color: "#2563eb",
    permissions: {
      "dashboard.view": true,
      "users.view": true,
      "users.edit": true,
      "users.delete": false,
      "users.token_adjust": true,
      "plans.view": true,
      "plans.edit": true,
      "plans.create": false,
      "plans.delete": false,
      "models.view": true,
      "models.manage": false,
      "servers.view": true,
      "billing.view": true,
      "billing.refund": false,
      "admins.view": true,
      "admins.create": false,
      "admins.edit": false,
      "admins.delete": false,
      "system.settings": false,
      "system.roles": false,
      "system.logs": true,
    },
  },
};

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function RolesPage() {
  const [roles, setRoles] = useState<RolePermissions>(DEFAULT_PERMISSIONS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [currentRole, setCurrentRole] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem("admin_user");
      if (raw) setCurrentRole(JSON.parse(raw).role || "");
    } catch {}
    fetchRoles();
  }, []);

  const fetchRoles = async () => {
    try {
      const resp = await fetch("/api/roles", { headers: authHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        if (data.permissions) setRoles(data.permissions);
      }
    } catch {}
    setLoading(false);
  };

  const handleToggle = (role: string, permKey: string) => {
    if (currentRole !== "SUPER_ADMIN") return;
    if (role === "SUPER_ADMIN") return; // 최고 관리자는 항상 모든 권한

    setRoles((prev) => ({
      ...prev,
      [role]: {
        ...prev[role],
        permissions: {
          ...prev[role].permissions,
          [permKey]: !prev[role].permissions[permKey],
        },
      },
    }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await fetch("/api/roles", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ permissions: roles }),
      });
      if (resp.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } else {
        const data = await resp.json();
        alert(data.error || "저장 실패");
      }
    } catch {}
    setSaving(false);
  };

  const allPermKeys = PERMISSION_GROUPS.flatMap((g) => g.items.map((i) => i.key));
  const roleKeys = ["SUPER_ADMIN", "ADMIN"];

  // 통계
  const adminPermCount = allPermKeys.filter((k) => roles.ADMIN?.permissions[k]).length;

  return (
    <div className="p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">롤(역할) 관리</h1>
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>역할별 권한 매트릭스 설정. SUPER_ADMIN은 모든 권한 고정.</p>
        </div>
        {currentRole === "SUPER_ADMIN" && (
          <button onClick={handleSave} disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: saved ? "#16a34a" : "var(--primary)" }}>
            {saving ? "저장 중..." : saved ? "저장 완료!" : "권한 저장"}
          </button>
        )}
      </div>

      {/* 역할 요약 카드 */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-3 h-3 rounded-full" style={{ background: "#7c3aed" }} />
            <div className="text-sm font-semibold">최고 관리자 (SUPER_ADMIN)</div>
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            모든 권한 ({allPermKeys.length}개) - 변경 불가
          </div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-3 h-3 rounded-full" style={{ background: "#2563eb" }} />
            <div className="text-sm font-semibold">관리자 (ADMIN)</div>
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            {adminPermCount}개 권한 활성 / {allPermKeys.length}개 중
          </div>
        </div>
        <div className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-3 h-3 rounded-full" style={{ background: "#6b7280" }} />
            <div className="text-sm font-semibold">일반 유저 (USER)</div>
          </div>
          <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            관리자 패널 접근 불가 (0개 권한)
          </div>
        </div>
      </div>

      {/* 권한 매트릭스 */}
      {loading ? (
        <div className="text-center py-12 text-sm" style={{ color: "var(--muted-foreground)" }}>로딩 중...</div>
      ) : (
        <div className="space-y-4">
          {PERMISSION_GROUPS.map((group) => (
            <div key={group.group} className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--background)" }}>
              <div className="px-5 py-3 font-semibold text-sm" style={{ background: "var(--muted)" }}>
                {group.group}
              </div>
              <table className="w-full">
                <thead>
                  <tr className="border-t" style={{ borderColor: "var(--border)" }}>
                    <th className="text-left text-xs font-medium px-5 py-2 w-1/3" style={{ color: "var(--muted-foreground)" }}>권한</th>
                    <th className="text-left text-xs font-medium px-5 py-2 w-1/3" style={{ color: "var(--muted-foreground)" }}>설명</th>
                    {roleKeys.map((rk) => (
                      <th key={rk} className="text-center text-xs font-medium px-3 py-2 w-[100px]"
                        style={{ color: roles[rk]?.color || "#6b7280" }}>
                        {roles[rk]?.label || rk}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {group.items.map((item) => (
                    <tr key={item.key} className="border-t" style={{ borderColor: "var(--border)" }}>
                      <td className="px-5 py-3 text-sm font-medium">{item.label}</td>
                      <td className="px-5 py-3 text-xs" style={{ color: "var(--muted-foreground)" }}>{item.desc}</td>
                      {roleKeys.map((rk) => {
                        const checked = roles[rk]?.permissions[item.key] ?? false;
                        const isSuperAdmin = rk === "SUPER_ADMIN";
                        const canEdit = currentRole === "SUPER_ADMIN" && !isSuperAdmin;
                        return (
                          <td key={rk} className="px-3 py-3 text-center">
                            <button
                              onClick={() => canEdit && handleToggle(rk, item.key)}
                              className="inline-flex items-center justify-center w-6 h-6 rounded-md text-xs transition-colors"
                              style={{
                                background: checked ? (isSuperAdmin ? "#ede9fe" : "#dbeafe") : "var(--muted)",
                                color: checked ? (isSuperAdmin ? "#7c3aed" : "#2563eb") : "#d1d5db",
                                cursor: canEdit ? "pointer" : "default",
                                opacity: isSuperAdmin ? 0.7 : 1,
                              }}
                              disabled={!canEdit}
                              title={isSuperAdmin ? "최고 관리자는 항상 모든 권한" : canEdit ? "클릭하여 토글" : "조회 전용"}>
                              {checked ? "✓" : "—"}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {/* 안내 */}
      <div className="mt-6 rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--muted)" }}>
        <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>
          <strong>참고:</strong> SUPER_ADMIN은 모든 권한이 고정되어 있어 변경할 수 없습니다.
          ADMIN 역할의 권한만 조정 가능하며, 변경 후 반드시 "권한 저장" 버튼을 눌러주세요.
          USER 역할은 관리자 패널에 접근할 수 없으므로 권한 설정이 필요 없습니다.
        </div>
      </div>
    </div>
  );
}
