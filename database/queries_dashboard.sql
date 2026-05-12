-- =============================================================================
-- Paste these into InsForge → Database → SQL Editor
-- (Connected as project DB owner / SQL Editor usually sees ALL rows despite RLS.)
-- =============================================================================

-- --- TODAY: every wizard check-in collected today (UTC day)
SELECT * FROM wellcare_v_checkins_today
ORDER BY submitted_at DESC;

-- --- TODAY: daily tracker chip rows for today
SELECT * FROM wellcare_v_daily_tracker_today;

-- --- HISTORY: last 100 check-ins, newest first (full story per user/profile)
SELECT * FROM wellcare_v_checkins_history
ORDER BY submitted_at DESC
LIMIT 100;

-- --- HISTORY: one person only (replace UUID + slug after sync exists)
-- SELECT * FROM wellcare_v_checkins_history
-- WHERE owner_user_id = '00000000-0000-0000-0000-000000000000'::uuid
--   AND profile_person_id = 'your_person_id_slug'
-- ORDER BY submitted_at ASC;

-- --- Sanity: row counts + last activity time
SELECT * FROM wellcare_v_stats_summary;

-- --- Raw tables (Table Editor works too)
SELECT * FROM wellcare_checkins ORDER BY submitted_at DESC LIMIT 50;
SELECT * FROM wellcare_profiles ORDER BY updated_at DESC NULLS LAST;
