-- ============================================================
-- HSEE Phase 1 — RLHFFeedback table (manual draft)
-- ============================================================
-- 이 파일은 자동 실행되지 않은 수동 초안입니다.
-- 실제 적용 절차:
--   1) 기존 마이그레이션 history 와의 충돌 여부 확인
--   2) 개발 환경:  cd modules/hwarang-web && npx prisma migrate dev --name add_rlhf_feedback
--      (이미 schema.prisma 에 model 정의 있음 — diff 만 새 SQL 로 생성됨)
--   3) 운영 환경:  npx prisma migrate deploy
--
-- ⚠ schema.prisma 의 RLHFFeedback (line 1497~1516) 를 base 로 하므로
--    Prisma 가 자동 생성하는 SQL 과 동일해야 함. 이 파일은 fallback 참고용.
-- ============================================================

CREATE TABLE IF NOT EXISTS "RLHFFeedback" (
  "id"             TEXT      NOT NULL PRIMARY KEY,
  "conversationId" TEXT,
  "userId"         TEXT      NOT NULL,
  "messageId"      TEXT,
  "domain"         TEXT,
  "modelName"      TEXT,
  "loraName"       TEXT,
  "rating"         INTEGER,
  "ratedAt"        TIMESTAMP(3),
  "editDistance"   DOUBLE PRECISION,
  "followupMsg"    TEXT,
  "isSatisfied"    BOOLEAN,
  "createdAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "RLHFFeedback_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS "RLHFFeedback_messageId_key"
  ON "RLHFFeedback"("messageId");

CREATE INDEX IF NOT EXISTS "RLHFFeedback_userId_createdAt_idx"
  ON "RLHFFeedback"("userId", "createdAt");

CREATE INDEX IF NOT EXISTS "RLHFFeedback_domain_isSatisfied_idx"
  ON "RLHFFeedback"("domain", "isSatisfied");

CREATE INDEX IF NOT EXISTS "RLHFFeedback_domain_createdAt_idx"
  ON "RLHFFeedback"("domain", "createdAt");
