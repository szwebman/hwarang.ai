/**
 * 도메인 라우팅 테이블 조회 — 어떤 도메인이 어떤 모델로 가는지.
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";

const DOMAINS = ["general", "coding", "legal", "tax", "medical", "reasoning"];

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

export async function GET(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "관리자 권한이 필요합니다" }, { status: 403 });
  }

  const allActive = await prisma.aIModel.findMany({
    where: { isActive: true },
    orderBy: [
      { isDomainDefault: "desc" },
      { isDefault: "desc" },
      { sortOrder: "asc" },
    ],
  });

  // 전역 기본 모델 (있을 때 카테고리 매칭 실패 시 폴백)
  const globalDefault = allActive.find((m) => m.isDefault) || allActive[0] || null;

  const routingTable = DOMAINS.map((domain) => {
    const candidates = allActive.filter((m) => m.category === domain);
    const selected = candidates[0] || null;
    const usedFallback = !selected && globalDefault !== null;
    return {
      domain,
      selected: selected
        ? {
            id: selected.id,
            name: selected.name,
            displayName: selected.displayName,
            backendId: selected.backendId,
            loraName: selected.loraName,
            isDomainDefault: selected.isDomainDefault,
            status: selected.status,
          }
        : usedFallback
        ? {
            id: globalDefault!.id,
            name: globalDefault!.name,
            displayName: globalDefault!.displayName + " (폴백)",
            backendId: globalDefault!.backendId,
            loraName: null,  // 폴백 시 LoRA 안 씀
            isDomainDefault: false,
            status: globalDefault!.status,
          }
        : null,
      candidateCount: candidates.length,
      usedFallback,
    };
  });

  return Response.json({
    routingTable,
    globalDefault: globalDefault
      ? {
          id: globalDefault.id,
          name: globalDefault.name,
          displayName: globalDefault.displayName,
          backendId: globalDefault.backendId,
        }
      : null,
  });
}
