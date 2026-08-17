CREATE TABLE IF NOT EXISTS runtime_schedule_events(
 event_id TEXT PRIMARY KEY,
 event_key TEXT NOT NULL UNIQUE,
 workflow_name TEXT NOT NULL,
 cycle_type TEXT,
 scheduled_at TEXT NOT NULL,
 started_at TEXT NOT NULL,
 completed_at TEXT,
 github_run_id TEXT,
 github_run_attempt TEXT,
 status TEXT NOT NULL,
 cycle_id TEXT,
 details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_runtime_schedule_events_time ON runtime_schedule_events(workflow_name, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS ix_runtime_schedule_events_status ON runtime_schedule_events(status, scheduled_at DESC);

CREATE TABLE IF NOT EXISTS runtime_validation_reports(
 report_id TEXT PRIMARY KEY,
 report_key TEXT NOT NULL UNIQUE,
 report_type TEXT NOT NULL,
 window_start TEXT NOT NULL,
 window_end TEXT NOT NULL,
 generated_at TEXT NOT NULL,
 summary_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_runtime_validation_reports_time ON runtime_validation_reports(report_type, generated_at DESC);
