-- 다중 인스턴스 cron job 분산 락
-- HWARANG_SCHEDULER_LEADER 환경변수 가드의 백업 안전망 (leader 2대 동시 사고 방지).

CREATE TABLE IF NOT EXISTS "scheduler_lock" (
    "job_name"    TEXT        NOT NULL,
    "host"        TEXT        NOT NULL,
    "acquired_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at"  TIMESTAMP(3) NOT NULL,
    CONSTRAINT "scheduler_lock_pkey" PRIMARY KEY ("job_name")
);

CREATE INDEX IF NOT EXISTS "scheduler_lock_expires_at_idx"
    ON "scheduler_lock" ("expires_at");
