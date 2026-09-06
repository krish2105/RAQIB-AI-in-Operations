-- RAQIB schema, generated from cloud/raqib_api/models.py. Apply in the Supabase SQL editor.
create extension if not exists vector;

CREATE TABLE sites (
	name VARCHAR NOT NULL, 
	profile VARCHAR NOT NULL, 
	tills INTEGER NOT NULL, 
	thresholds JSON, 
	floor JSON, 
	machines JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (name)
);

CREATE INDEX ix_sites_profile ON sites (profile);

CREATE TABLE events (
	id VARCHAR NOT NULL, 
	site VARCHAR NOT NULL, 
	camera VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	kind VARCHAR NOT NULL, 
	severity INTEGER NOT NULL, 
	payload JSON, 
	clip_path VARCHAR, 
	rule_id VARCHAR NOT NULL, 
	received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	handled BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_events_kind ON events (kind);

CREATE INDEX ix_events_ts ON events (ts);

CREATE INDEX ix_events_severity ON events (severity);

CREATE INDEX ix_events_handled ON events (handled);

CREATE INDEX ix_events_site ON events (site);

CREATE TABLE forecasts (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	target VARCHAR NOT NULL, 
	key VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	value FLOAT NOT NULL, 
	baseline_value FLOAT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_forecasts_site ON forecasts (site);

CREATE INDEX ix_forecasts_target ON forecasts (target);

CREATE TABLE documents (
	id VARCHAR NOT NULL, 
	site VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	path VARCHAR NOT NULL, 
	sha256 VARCHAR NOT NULL, 
	lang VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	meta JSON, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_documents_site ON documents (site);

CREATE INDEX ix_documents_kind ON documents (kind);

CREATE TABLE memories (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	agent VARCHAR NOT NULL, 
	key VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	source VARCHAR NOT NULL, 
	event_id VARCHAR, 
	written_by VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	pinned BOOLEAN NOT NULL, 
	quarantined BOOLEAN NOT NULL, 
	quarantine_reason VARCHAR, 
	sha256 VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_memories_key ON memories (key);

CREATE INDEX ix_memories_quarantined ON memories (quarantined);

CREATE INDEX ix_memories_site ON memories (site);

CREATE INDEX ix_memories_agent ON memories (agent);

CREATE INDEX ix_memories_event_id ON memories (event_id);

CREATE TABLE agent_runs (
	id VARCHAR NOT NULL, 
	site VARCHAR NOT NULL, 
	agent VARCHAR NOT NULL, 
	trigger VARCHAR NOT NULL, 
	started TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	ended TIMESTAMP WITHOUT TIME ZONE, 
	tool_calls INTEGER NOT NULL, 
	tokens INTEGER NOT NULL, 
	cost_usd FLOAT NOT NULL, 
	status VARCHAR NOT NULL, 
	meta JSON, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_agent_runs_agent ON agent_runs (agent);

CREATE INDEX ix_agent_runs_site ON agent_runs (site);

CREATE INDEX ix_agent_runs_status ON agent_runs (status);

CREATE TABLE users (
	id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	site_ids JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE stores (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	site_ids JSON, 
	region VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE drift_samples (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	camera VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	det_count FLOAT NOT NULL, 
	mean_conf FLOAT NOT NULL, 
	brightness FLOAT NOT NULL, 
	blur FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_drift_samples_site ON drift_samples (site);

CREATE INDEX ix_drift_samples_camera ON drift_samples (camera);

CREATE INDEX ix_drift_samples_ts ON drift_samples (ts);

CREATE TABLE quota_counters (
	provider VARCHAR NOT NULL, 
	day VARCHAR NOT NULL, 
	requests INTEGER NOT NULL, 
	tokens INTEGER NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (provider, day)
);

CREATE TABLE cameras (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	source VARCHAR NOT NULL, 
	fps FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site) REFERENCES sites (name)
);

CREATE INDEX ix_cameras_site ON cameras (site);

CREATE TABLE zones (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	camera VARCHAR NOT NULL, 
	polygon JSON, 
	meta JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(site) REFERENCES sites (name)
);

CREATE INDEX ix_zones_site ON zones (site);

CREATE TABLE clips (
	event_id VARCHAR NOT NULL, 
	path VARCHAR NOT NULL, 
	bytes INTEGER NOT NULL, 
	uploaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(event_id) REFERENCES events (id)
);

CREATE TABLE actions (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	event_id VARCHAR, 
	tool VARCHAR NOT NULL, 
	args JSON, 
	status VARCHAR NOT NULL, 
	autonomous BOOLEAN NOT NULL, 
	reasoning VARCHAR NOT NULL, 
	confidence FLOAT NOT NULL, 
	backend VARCHAR NOT NULL, 
	result JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	decided_at TIMESTAMP WITHOUT TIME ZONE, 
	decided_by VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES events (id)
);

CREATE INDEX ix_actions_site ON actions (site);

CREATE INDEX ix_actions_status ON actions (status);

CREATE INDEX ix_actions_event_id ON actions (event_id);

CREATE INDEX ix_actions_tool ON actions (tool);

CREATE TABLE captions (
	id SERIAL NOT NULL, 
	event_id VARCHAR NOT NULL, 
	site VARCHAR NOT NULL, 
	camera VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	text VARCHAR NOT NULL, 
	parsed JSON, 
	model VARCHAR NOT NULL, 
	provider VARCHAR NOT NULL, 
	frames INTEGER NOT NULL, 
	tokens_in INTEGER NOT NULL, 
	tokens_out INTEGER NOT NULL, 
	cost_usd FLOAT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES events (id)
);

CREATE INDEX ix_captions_site ON captions (site);

CREATE INDEX ix_captions_event_id ON captions (event_id);

CREATE TABLE chunks (
	id VARCHAR NOT NULL, 
	site VARCHAR NOT NULL, 
	doc_id VARCHAR, 
	event_id VARCHAR, 
	kind VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	text VARCHAR NOT NULL, 
	embedding VECTOR(1024), 
	model VARCHAR NOT NULL, 
	meta JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doc_id) REFERENCES documents (id), 
	FOREIGN KEY(event_id) REFERENCES events (id)
);

CREATE INDEX ix_chunks_event_id ON chunks (event_id);

CREATE INDEX ix_chunks_doc_id ON chunks (doc_id);

CREATE INDEX ix_chunks_site ON chunks (site);

CREATE INDEX ix_chunks_kind ON chunks (kind);

CREATE INDEX ix_chunks_ts ON chunks (ts);

CREATE TABLE agent_messages (
	id VARCHAR NOT NULL, 
	run_id VARCHAR NOT NULL, 
	from_agent VARCHAR NOT NULL, 
	to_agent VARCHAR NOT NULL, 
	schema VARCHAR NOT NULL, 
	payload JSON, 
	hmac VARCHAR NOT NULL, 
	nonce VARCHAR NOT NULL, 
	ts TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	verified BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id)
);

CREATE INDEX ix_agent_messages_run_id ON agent_messages (run_id);

CREATE TABLE tool_calls (
	id SERIAL NOT NULL, 
	site VARCHAR NOT NULL, 
	action_id INTEGER, 
	tool VARCHAR NOT NULL, 
	input JSON, 
	output JSON, 
	ok BOOLEAN NOT NULL, 
	error VARCHAR, 
	latency_ms FLOAT NOT NULL, 
	cost_usd FLOAT NOT NULL, 
	backend VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(action_id) REFERENCES actions (id)
);

CREATE INDEX ix_tool_calls_site ON tool_calls (site);

-- v2 extras: ANN index, full-text column, row level security (API role bypasses RLS)
create index if not exists ix_chunks_embedding_hnsw on chunks using hnsw (embedding vector_cosine_ops);
alter table chunks add column if not exists tsv tsvector generated always as (to_tsvector('simple', coalesce(text, ''))) stored;
create index if not exists ix_chunks_tsv on chunks using gin (tsv);
alter table sites enable row level security;
alter table cameras enable row level security;
alter table zones enable row level security;
alter table events enable row level security;
alter table clips enable row level security;
alter table actions enable row level security;
alter table tool_calls enable row level security;
alter table forecasts enable row level security;
alter table captions enable row level security;
alter table documents enable row level security;
alter table chunks enable row level security;
alter table memories enable row level security;
alter table agent_runs enable row level security;
alter table agent_messages enable row level security;
alter table users enable row level security;
alter table stores enable row level security;
alter table drift_samples enable row level security;
alter table quota_counters enable row level security;
