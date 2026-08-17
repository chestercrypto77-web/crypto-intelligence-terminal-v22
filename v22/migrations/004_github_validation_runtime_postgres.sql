CREATE TABLE IF NOT EXISTS runtime_schedule_events(
 event_id UUID PRIMARY KEY,
 event_key TEXT NOT NULL UNIQUE,
 workflow_name TEXT NOT NULL,
 cycle_type TEXT,
 scheduled_at TIMESTAMPTZ NOT NULL,
 started_at TIMESTAMPTZ NOT NULL,
 completed_at TIMESTAMPTZ,
 github_run_id TEXT,
 github_run_attempt TEXT,
 status TEXT NOT NULL,
 cycle_id UUID,
 details_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_runtime_schedule_events_time ON runtime_schedule_events(workflow_name, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS ix_runtime_schedule_events_status ON runtime_schedule_events(status, scheduled_at DESC);

CREATE TABLE IF NOT EXISTS runtime_validation_reports(
 report_id UUID PRIMARY KEY,
 report_key TEXT NOT NULL UNIQUE,
 report_type TEXT NOT NULL,
 window_start TIMESTAMPTZ NOT NULL,
 window_end TIMESTAMPTZ NOT NULL,
 generated_at TIMESTAMPTZ NOT NULL,
 summary_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_runtime_validation_reports_time ON runtime_validation_reports(report_type, generated_at DESC);
