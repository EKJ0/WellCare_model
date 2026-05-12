-- =============================================================================
-- WellCare / burnout check-in — cloud persistence schema (InsForge / Postgres)
--
-- ISOLATION MODEL (training-safe):
--   * Every row is scoped by owner_user_id  → authenticated InsForge / JWT user.
--   * Within an account, profile_person_id → app's stable ML identity (personId).
--     NEVER merge rows across different profile_person_id values when training.
--
-- Apply via InsForge SQL runner or:
--   npx @insforge/cli db query "<escaped-SQL>"
--
-- RLS expects Supabase-style auth.uid(); adjust policy expressions if your
-- InsForge project exposes a different session UID helper.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Profile definitions (one row per person-avatar inside an account)
-- Mirrors client objects from burnout_profiles_v1 (excluding secrets — sync auth separately).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellcare_profiles (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id             UUID NOT NULL,

  client_profile_id       TEXT NOT NULL,
  profile_person_id       TEXT NOT NULL,

  display_name              TEXT NOT NULL,
  email_local               TEXT,
  avatar_color              TEXT,

  created_at_ms           BIGINT,
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT wellcare_profiles_unique_person
    UNIQUE (owner_user_id, profile_person_id),
  CONSTRAINT wellcare_profiles_unique_client
    UNIQUE (owner_user_id, client_profile_id)
);

COMMENT ON TABLE wellcare_profiles IS
  'Per-user personas for ML/training; profile_person_id must match CSV person_id / history.person_id.';

CREATE INDEX IF NOT EXISTS wellcare_profiles_owner_idx
  ON wellcare_profiles (owner_user_id);


-- ---------------------------------------------------------------------------
-- Wizard check-ins — raw timeline used for dashboards & future model fitting.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellcare_checkins (
  id                      BIGSERIAL PRIMARY KEY,
  owner_user_id           UUID NOT NULL,
  profile_person_id       TEXT NOT NULL,

  client_row_id           BIGINT,
  submitted_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

  feeling                 TEXT,

  risk_probability        DOUBLE PRECISION NOT NULL,
  verdict_label           TEXT,

  notes                   TEXT,

  signals_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
  events_chips_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
  events_model_json       JSONB NOT NULL DEFAULT '[]'::jsonb,

  hybrid_explain          TEXT,
  hybrid_action           TEXT,
  safety_net_suggested    BOOLEAN DEFAULT FALSE,

  CONSTRAINT wellcare_checkins_profile_fk
    FOREIGN KEY (owner_user_id, profile_person_id)
    REFERENCES wellcare_profiles (owner_user_id, profile_person_id)
    ON DELETE CASCADE
);

COMMENT ON COLUMN wellcare_checkins.signals_json IS
  '{hours,sleep,mood,stress,mgr_support,peer_support,deadline_pressure,on_call_load}';

CREATE INDEX IF NOT EXISTS wellcare_checkins_person_time_idx
  ON wellcare_checkins (owner_user_id, profile_person_id, submitted_at DESC);


-- ---------------------------------------------------------------------------
-- Daily tracker chips — nested map person × calendar day × categories.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellcare_daily_tracker_days (
  owner_user_id           UUID NOT NULL,
  profile_person_id       TEXT NOT NULL,
  day_date                DATE NOT NULL,

  categories_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (owner_user_id, profile_person_id, day_date),

  CONSTRAINT wellcare_tracker_profile_fk
    FOREIGN KEY (owner_user_id, profile_person_id)
    REFERENCES wellcare_profiles (owner_user_id, profile_person_id)
    ON DELETE CASCADE
);

COMMENT ON COLUMN wellcare_daily_tracker_days.categories_json IS
  'Keys: energy, overwhelm, motivation, sleepQuality, hydration, movement, breaks, screenTime, caffeine, workStudyPressure, socialExhaustion, alcohol, nicotine';


-- ---------------------------------------------------------------------------
-- Device-wide preferences for the signed-in account (theme, reminders, active profile).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellcare_owner_settings (
  owner_user_id           UUID PRIMARY KEY,

  theme                   TEXT,
  reminder_dow            SMALLINT,
  active_profile_client_id TEXT,

  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- Safety Net invites — stored per profile_person_id so circles never cross people.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellcare_safety_net_contacts (
  owner_user_id           UUID NOT NULL,
  profile_person_id       TEXT NOT NULL,

  contacts_json           JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (owner_user_id, profile_person_id),

  CONSTRAINT wellcare_safety_profile_fk
    FOREIGN KEY (owner_user_id, profile_person_id)
    REFERENCES wellcare_profiles (owner_user_id, profile_person_id)
    ON DELETE CASCADE
);


-- ---------------------------------------------------------------------------
-- Optional per-person imported / personalized model bundle for on-device parity.
-- Large JSON — query selectively in application code.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellcare_personal_model_bundles (
  owner_user_id           UUID NOT NULL,
  profile_person_id       TEXT NOT NULL,

  bundle_json             JSONB NOT NULL,
  source                  TEXT DEFAULT 'import',
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (owner_user_id, profile_person_id),

  CONSTRAINT wellcare_bundle_profile_fk
    FOREIGN KEY (owner_user_id, profile_person_id)
    REFERENCES wellcare_profiles (owner_user_id, profile_person_id)
    ON DELETE CASCADE
);


-- =============================================================================
-- Row Level Security — strict tenant isolation
-- =============================================================================

ALTER TABLE wellcare_profiles               ENABLE ROW LEVEL SECURITY;
ALTER TABLE wellcare_checkins               ENABLE ROW LEVEL SECURITY;
ALTER TABLE wellcare_daily_tracker_days     ENABLE ROW LEVEL SECURITY;
ALTER TABLE wellcare_owner_settings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE wellcare_safety_net_contacts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE wellcare_personal_model_bundles ENABLE ROW LEVEL SECURITY;

-- Drop policies if re-running script (idempotent in dev)
DROP POLICY IF EXISTS wellcare_profiles_select ON wellcare_profiles;
DROP POLICY IF EXISTS wellcare_profiles_modify ON wellcare_profiles;
DROP POLICY IF EXISTS wellcare_checkins_select ON wellcare_checkins;
DROP POLICY IF EXISTS wellcare_checkins_modify ON wellcare_checkins;
DROP POLICY IF EXISTS wellcare_tracker_select ON wellcare_daily_tracker_days;
DROP POLICY IF EXISTS wellcare_tracker_modify ON wellcare_daily_tracker_days;
DROP POLICY IF EXISTS wellcare_owner_settings_select ON wellcare_owner_settings;
DROP POLICY IF EXISTS wellcare_owner_settings_modify ON wellcare_owner_settings;
DROP POLICY IF EXISTS wellcare_safety_select ON wellcare_safety_net_contacts;
DROP POLICY IF EXISTS wellcare_safety_modify ON wellcare_safety_net_contacts;
DROP POLICY IF EXISTS wellcare_bundle_select ON wellcare_personal_model_bundles;
DROP POLICY IF EXISTS wellcare_bundle_modify ON wellcare_personal_model_bundles;

CREATE POLICY wellcare_profiles_select ON wellcare_profiles
  FOR SELECT USING (owner_user_id = auth.uid());

CREATE POLICY wellcare_profiles_modify ON wellcare_profiles
  FOR ALL USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY wellcare_checkins_select ON wellcare_checkins
  FOR SELECT USING (owner_user_id = auth.uid());

CREATE POLICY wellcare_checkins_modify ON wellcare_checkins
  FOR ALL USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY wellcare_tracker_select ON wellcare_daily_tracker_days
  FOR SELECT USING (owner_user_id = auth.uid());

CREATE POLICY wellcare_tracker_modify ON wellcare_daily_tracker_days
  FOR ALL USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY wellcare_owner_settings_select ON wellcare_owner_settings
  FOR SELECT USING (owner_user_id = auth.uid());

CREATE POLICY wellcare_owner_settings_modify ON wellcare_owner_settings
  FOR ALL USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY wellcare_safety_select ON wellcare_safety_net_contacts
  FOR SELECT USING (owner_user_id = auth.uid());

CREATE POLICY wellcare_safety_modify ON wellcare_safety_net_contacts
  FOR ALL USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

CREATE POLICY wellcare_bundle_select ON wellcare_personal_model_bundles
  FOR SELECT USING (owner_user_id = auth.uid());

CREATE POLICY wellcare_bundle_modify ON wellcare_personal_model_bundles
  FOR ALL USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

-- -----------------------------------------------------------------------------
-- Grants (uncomment / adapt for your InsForge role names)
-- -----------------------------------------------------------------------------
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
