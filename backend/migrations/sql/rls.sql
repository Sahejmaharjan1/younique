DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'younique_app') THEN
    CREATE ROLE younique_app LOGIN PASSWORD 'younique_app' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

ALTER ROLE younique_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

CREATE OR REPLACE FUNCTION app.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END
$fn$;

CREATE OR REPLACE FUNCTION app.forbid_consent_update() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
  IF OLD.effective_at <= now() THEN
    RAISE EXCEPTION 'consent documents are immutable after effective_at';
  END IF;
  RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS trg_consent_immutable ON app.consent_documents;
CREATE TRIGGER trg_consent_immutable
  BEFORE UPDATE ON app.consent_documents
  FOR EACH ROW EXECUTE FUNCTION app.forbid_consent_update();

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT table_schema, table_name
    FROM information_schema.columns
    WHERE column_name = 'updated_at' AND table_schema = 'app'
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_set_updated_at ON %I.%I', r.table_schema, r.table_name);
    EXECUTE format(
      'CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON %I.%I FOR EACH ROW EXECUTE FUNCTION app.set_updated_at()',
      r.table_schema, r.table_name
    );
  END LOOP;
END
$$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'invitations','encryption_keys','idempotency_keys','memory_sets',
    'chats','messages','message_parts','runs','run_steps','run_events','approvals','tool_policies',
    'artifacts','artifact_versions','artifact_scans','chat_artifacts','provider_keys','connections',
    'connection_grants','connection_secrets','oauth_states','oauth_clients','resource_grants',
    'share_links','usage_events','usage_request_dedupe','agents','agent_versions','pipelines',
    'pipeline_versions','pats','webhook_nonces'
  ]
  LOOP
    EXECUTE format('ALTER TABLE app.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE app.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON app.%I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON app.%I USING (workspace_id = NULLIF(current_setting(''app.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting(''app.workspace_id'', true), '''')::uuid)',
      t
    );
  END LOOP;
END
$$;

ALTER TABLE app.workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.workspace_members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON app.workspace_members;
CREATE POLICY tenant_isolation ON app.workspace_members
  USING (
    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    OR user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
  )
  WITH CHECK (workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid);

DROP POLICY IF EXISTS tenant_isolation ON app.share_links;
CREATE POLICY tenant_isolation ON app.share_links
  USING (
    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    OR token_hash = NULLIF(current_setting('app.share_token_hash', true), '')
  )
  WITH CHECK (workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid);

ALTER TABLE app.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.workspaces FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON app.workspaces;
CREATE POLICY tenant_isolation ON app.workspaces
  USING (
    id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    OR EXISTS (
      SELECT 1 FROM app.workspace_members AS member_row
      WHERE member_row.workspace_id = workspaces.id
        AND member_row.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        AND member_row.archived_at IS NULL
    )
    OR current_setting('app.bootstrap', true) = 'on'
  )
  WITH CHECK (
    id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  );

DROP POLICY IF EXISTS outbox_isolation ON app.outbox;
DROP POLICY IF EXISTS tenant_isolation ON app.outbox;
CREATE POLICY tenant_isolation ON app.outbox
  USING (
    workspace_id IS NULL
    OR workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
  )
  WITH CHECK (
    workspace_id IS NULL
    OR workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
  );

ALTER TABLE app.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_all ON app.users;
CREATE POLICY users_all ON app.users
  USING (
    id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  )
  WITH CHECK (
    id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  );

ALTER TABLE app.identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.identities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS identities_all ON app.identities;
CREATE POLICY identities_all ON app.identities
  USING (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR firebase_uid = NULLIF(current_setting('app.firebase_uid', true), '')
    OR current_setting('app.bootstrap', true) = 'on'
  )
  WITH CHECK (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  );

ALTER TABLE app.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.devices FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS devices_all ON app.devices;
CREATE POLICY devices_all ON app.devices
  USING (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  )
  WITH CHECK (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  );

ALTER TABLE app.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sessions_all ON app.sessions;
CREATE POLICY sessions_all ON app.sessions
  USING (
    token_hash = NULLIF(current_setting('app.session_token_hash', true), '')
    OR user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR session_group_id = NULLIF(current_setting('app.session_group_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  )
  WITH CHECK (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  );

ALTER TABLE app.consent_acceptances ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.consent_acceptances FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS consent_accept_all ON app.consent_acceptances;
CREATE POLICY consent_accept_all ON app.consent_acceptances
  USING (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  )
  WITH CHECK (
    user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
    OR current_setting('app.bootstrap', true) = 'on'
  );

ALTER TABLE app.consent_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.consent_documents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS consent_read ON app.consent_documents;
CREATE POLICY consent_read ON app.consent_documents FOR SELECT USING (true);

ALTER TABLE app.model_providers ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.model_providers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS providers_read ON app.model_providers;
CREATE POLICY providers_read ON app.model_providers FOR SELECT USING (true);

ALTER TABLE app.models ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.models FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS models_read ON app.models;
DROP POLICY IF EXISTS models_write ON app.models;
CREATE POLICY models_read ON app.models FOR SELECT USING (
  workspace_id IS NULL
  OR workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
);
CREATE POLICY models_write ON app.models FOR INSERT WITH CHECK (
  workspace_id IS NOT NULL
  AND workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
);
CREATE POLICY models_update ON app.models FOR UPDATE USING (
  workspace_id IS NOT NULL
  AND workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
);

ALTER TABLE app.model_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.model_prices FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS prices_read ON app.model_prices;
CREATE POLICY prices_read ON app.model_prices FOR SELECT USING (true);

ALTER TABLE audit.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.audit_logs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_insert ON audit.audit_logs;
CREATE POLICY audit_insert ON audit.audit_logs FOR INSERT WITH CHECK (
  workspace_id IS NULL
  OR workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
);

CREATE TABLE IF NOT EXISTS app.usage_events_default PARTITION OF app.usage_events DEFAULT;
CREATE TABLE IF NOT EXISTS app.run_events_default PARTITION OF app.run_events DEFAULT;
CREATE TABLE IF NOT EXISTS audit.audit_logs_default PARTITION OF audit.audit_logs DEFAULT;

GRANT USAGE ON SCHEMA app TO younique_app;
GRANT USAGE ON SCHEMA audit TO younique_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO younique_app;
GRANT INSERT ON ALL TABLES IN SCHEMA audit TO younique_app;

INSERT INTO app.consent_documents (id, kind, version, content_sha256, summary_of_changes, url, is_required, effective_at)
VALUES
  ('00000000-0000-7000-8000-000000000001', 'terms', 1, repeat('a', 64), 'Initial terms', '/legal/terms/v1', true, now()),
  ('00000000-0000-7000-8000-000000000002', 'privacy', 1, repeat('b', 64), 'Initial privacy policy', '/legal/privacy/v1', true, now()),
  ('00000000-0000-7000-8000-000000000003', 'ai_data_use', 1, repeat('c', 64), 'Initial AI data use terms', '/legal/ai-data-use/v1', true, now())
ON CONFLICT DO NOTHING;

INSERT INTO app.model_providers (id, key, display_name, auth_kind)
VALUES
  ('00000000-0000-7000-8000-000000000011', 'anthropic', 'Anthropic', 'api_key'),
  ('00000000-0000-7000-8000-000000000012', 'openai', 'OpenAI', 'api_key'),
  ('00000000-0000-7000-8000-000000000013', 'google', 'Google', 'api_key'),
  ('00000000-0000-7000-8000-000000000014', 'openai_compatible', 'OpenAI compatible', 'api_key'),
  ('00000000-0000-7000-8000-000000000015', 'fake', 'Fake', 'api_key')
ON CONFLICT DO NOTHING;

INSERT INTO app.models (
  id, provider_id, workspace_id, model_ref, display_name, context_window, max_output_tokens,
  supports_tools, supports_reasoning, supports_vision, reasoning_control, status, capabilities
)
VALUES
  ('00000000-0000-7000-8000-000000000021', '00000000-0000-7000-8000-000000000011', NULL, 'claude-sonnet-4-5', 'Claude Sonnet 4.5', 200000, 8192, true, true, true, 'budget_tokens', 'active', '{}'),
  ('00000000-0000-7000-8000-000000000022', '00000000-0000-7000-8000-000000000012', NULL, 'gpt-4.1', 'GPT-4.1', 128000, 8192, true, false, true, 'none', 'active', '{}'),
  ('00000000-0000-7000-8000-000000000023', '00000000-0000-7000-8000-000000000015', NULL, 'fake-chat', 'Fake chat', 32000, 4096, true, true, false, 'boolean', 'active', '{}')
ON CONFLICT DO NOTHING;

INSERT INTO app.model_prices (
  id, model_id, input_micro_usd_per_mtok, output_micro_usd_per_mtok,
  cached_input_micro_usd_per_mtok, reasoning_micro_usd_per_mtok, effective_from
)
VALUES
  ('00000000-0000-7000-8000-000000000031', '00000000-0000-7000-8000-000000000021', 3000000, 15000000, 300000, 15000000, now()),
  ('00000000-0000-7000-8000-000000000032', '00000000-0000-7000-8000-000000000022', 2000000, 8000000, 500000, 0, now()),
  ('00000000-0000-7000-8000-000000000033', '00000000-0000-7000-8000-000000000023', 0, 0, 0, 0, now())
ON CONFLICT DO NOTHING;
