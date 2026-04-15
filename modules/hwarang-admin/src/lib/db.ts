/**
 * Admin DB 연결.
 * 관리자 앱은 직접 DB 접근 대신 API로 데이터를 가져옵니다.
 * DB가 필요한 경우를 위해 빈 객체 제공.
 */

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

// Prisma 대신 API 호출로 데이터 접근
export const prisma = {
  user: { count: async () => 0, findMany: async () => [], groupBy: async () => [] },
  plan: { findMany: async () => [] },
  usageRecord: { count: async () => 0 },
  payment: { aggregate: async () => ({ _sum: { amount: 0 } }) },
} as any;

export { HWARANG_API_URL };
