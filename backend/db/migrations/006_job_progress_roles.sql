ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS progress_roles_json JSONB NOT NULL DEFAULT '[]'::jsonb;
