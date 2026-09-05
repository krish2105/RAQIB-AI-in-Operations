-- RAQIB schema, generated from cloud/raqib_api/models.py. Apply in the Supabase SQL editor.

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

CREATE INDEX ix_events_handled ON events (handled);

CREATE INDEX ix_events_site ON events (site);

CREATE INDEX ix_events_kind ON events (kind);

CREATE INDEX ix_events_ts ON events (ts);

CREATE INDEX ix_events_severity ON events (severity);

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

CREATE INDEX ix_actions_tool ON actions (tool);

CREATE INDEX ix_actions_site ON actions (site);

CREATE INDEX ix_actions_status ON actions (status);

CREATE INDEX ix_actions_event_id ON actions (event_id);

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

