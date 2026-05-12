-- =============================================================================
-- WellCare — InsForge dashboard helpers (views + fixes)
-- Run AFTER schema_wellcare.sql
--
-- In InsForge: Dashboard → Database → SQL Editor (or Migrations).
--
-- VIEWING DATA IN THE UI
--   • Tables appear under Database → Tables (names prefixed wellcare_*).
--   • For blank tables: the HTML app still uses localStorage only until you
--     wire InsForge Auth + REST/sync — sync code pushes rows here.
-- =============================================================================

-- Back-fill verdict column if you ran an older schema without it.
ALTER TABLE wellcare_checkins
  ADD COLUMN IF NOT EXISTS verdict_label TEXT;

-- Composite FK-compatible join helper pattern used below:
--   JOIN wellcare_profiles p
--     ON p.owner_user_id = c.owner_user_id
--    AND p.profile_person_id = c.profile_person_id

-- ---------------------------------------------------------------------------
-- Today's wizard check-ins (calendar day in UTC — aligns with typical PG NOW())
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW wellcare_v_checkins_today AS
SELECT
  c.id,
  c.submitted_at,
  (c.submitted_at AT TIME ZONE 'UTC')::date AS day_utc,
  c.owner_user_id,
  c.profile_person_id,
  p.display_name,
  p.email_local,
  c.feeling,
  c.verdict_label,
  c.risk_probability,
  round((c.risk_probability * 100)::numeric, 1) AS risk_percent,
  (c.signals_json->>'stress')::numeric AS stress,
  (c.signals_json->>'mood')::numeric AS mood,
  (c.signals_json->>'sleep')::numeric AS sleep_hours,
  (c.signals_json->>'hours')::numeric AS work_hours,
  c.signals_json,
  c.events_chips_json,
  c.notes,
  c.hybrid_explain,
  c.safety_net_suggested
FROM wellcare_checkins c
JOIN wellcare_profiles p
  ON p.owner_user_id = c.owner_user_id
 AND p.profile_person_id = c.profile_person_id
WHERE (c.submitted_at AT TIME ZONE 'UTC')::date
      = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date;

COMMENT ON VIEW wellcare_v_checkins_today IS
  'All check-ins submitted today (UTC). Use in SQL Editor for daily ops review.';


-- ---------------------------------------------------------------------------
-- Full chronological history — readable columns + JSON for drill-down
-- (history-first; default recent-first ordering when you SELECT … ORDER BY)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW wellcare_v_checkins_history AS
SELECT
  c.id,
  c.submitted_at,
  (c.submitted_at AT TIME ZONE 'UTC')::date AS day_utc,
  c.owner_user_id,
  c.profile_person_id,
  p.display_name,
  p.email_local,
  c.feeling,
  c.verdict_label,
  c.risk_probability,
  round((c.risk_probability * 100)::numeric, 1) AS risk_percent,
  (c.signals_json->>'stress')::numeric AS stress,
  (c.signals_json->>'mood')::numeric AS mood,
  (c.signals_json->>'sleep')::numeric AS sleep_hours,
  (c.signals_json->>'hours')::numeric AS work_hours,
  (c.signals_json->>'deadline_pressure')::numeric AS deadline_pressure,
  c.signals_json,
  c.events_chips_json,
  c.events_model_json,
  c.notes,
  c.hybrid_explain,
  c.hybrid_action,
  c.safety_net_suggested,
  c.client_row_id
FROM wellcare_checkins c
JOIN wellcare_profiles p
  ON p.owner_user_id = c.owner_user_id
 AND p.profile_person_id = c.profile_person_id;

COMMENT ON VIEW wellcare_v_checkins_history IS
  'Complete multi-user timeline with joins; ORDER BY submitted_at DESC for newest-first.';


-- ---------------------------------------------------------------------------
-- Today's daily-tracker chip saves (per person / profile)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW wellcare_v_daily_tracker_today AS
SELECT
  t.owner_user_id,
  t.profile_person_id,
  p.display_name,
  t.day_date,
  t.categories_json,
  t.updated_at
FROM wellcare_daily_tracker_days t
JOIN wellcare_profiles p
  ON p.owner_user_id = t.owner_user_id
 AND p.profile_person_id = t.profile_person_id
WHERE t.day_date = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date;

COMMENT ON VIEW wellcare_v_daily_tracker_today IS
  'Category chips logged for the current UTC calendar day.';


-- ---------------------------------------------------------------------------
-- Quick counts — sanity check that ingestion is working
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW wellcare_v_stats_summary AS
SELECT
  (SELECT count(*) FROM wellcare_profiles) AS profile_rows,
  (SELECT count(*) FROM wellcare_checkins) AS checkin_rows,
  (SELECT count(*) FROM wellcare_daily_tracker_days) AS tracker_day_rows,
  (SELECT count(*) FROM wellcare_v_checkins_today) AS checkins_today,
  (SELECT max(submitted_at) FROM wellcare_checkins) AS last_checkin_at;
