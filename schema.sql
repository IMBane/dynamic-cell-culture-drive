CREATE TABLE IF NOT EXISTS tilt_entry_table (
	id SERIAL PRIMARY KEY,
	tilt_scenario_id INTEGER DEFAULT NULL,
	scenario_name VARCHAR(255) DEFAULT NULL,
	name VARCHAR(255) NOT NULL,
	measurement_timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS rotation_entry_table (
	id SERIAL PRIMARY KEY,
	rotary_scenario_id INTEGER DEFAULT NULL,
	scenario_name VARCHAR(255) DEFAULT NULL,
	name VARCHAR(255) NOT NULL,
	measurement_timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS peristaltic_entry_table (
	id SERIAL PRIMARY KEY,
	peristaltic_scenario_id INTEGER DEFAULT NULL,
	scenario_name VARCHAR(255) DEFAULT NULL,
	name VARCHAR(255) NOT NULL,
	measurement_timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS tilt_scenarios (
	id SERIAL PRIMARY KEY,
	name VARCHAR(255) NOT NULL,
	-- 'constant' uses all movement fields below except frequency.
	-- 'sinusoidal' uses frequency, min_tilt, max_tilt and repetitions; the
	-- other movement fields are NULL.
	movement_mode VARCHAR(20) NOT NULL DEFAULT 'constant' CHECK (movement_mode IN ('constant', 'sinusoidal')),
	frequency FLOAT CHECK (frequency > 0),
	microstepping INT,
	min_tilt INT,
	max_tilt INT,
	move_duration FLOAT,
	repetitions INT,
	end_position INT,
	standstill_duration_left FLOAT,
	standstill_duration_horizontal FLOAT,
	standstill_duration_right FLOAT,
	is_active BOOLEAN NOT NULL DEFAULT TRUE
	CONSTRAINT tilt_scenarios_mode_fields_check CHECK (
		(
			movement_mode = 'sinusoidal'
			AND frequency IS NOT NULL
			AND min_tilt IS NOT NULL
			AND max_tilt IS NOT NULL
			AND repetitions IS NOT NULL
		)
		OR (
			movement_mode = 'constant'
			AND microstepping IS NOT NULL
			AND min_tilt IS NOT NULL
			AND max_tilt IS NOT NULL
			AND move_duration IS NOT NULL
			AND repetitions IS NOT NULL
			AND end_position IS NOT NULL
			AND standstill_duration_left IS NOT NULL
			AND standstill_duration_horizontal IS NOT NULL
			AND standstill_duration_right IS NOT NULL
		)
	)
);

CREATE TABLE IF NOT EXISTS rotary_scenarios (
	id SERIAL PRIMARY KEY,
	name VARCHAR(255) NOT NULL,
	movements JSONB NOT NULL,
	is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS peristaltic_scenarios (
	id SERIAL PRIMARY KEY,
	name VARCHAR(255) NOT NULL,
	movements JSONB NOT NULL,
	calibration JSONB NOT NULL,
	is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS tilt_measurements (
	id SERIAL,
	entry_id INTEGER NOT NULL,
	angle FLOAT NOT NULL,
	state TEXT CHECK (state IN ('moving', 'idle', 'error')) NOT NULL,
	time float NOT NULL,
	PRIMARY KEY (id, time)
);

CREATE TABLE IF NOT EXISTS peristaltic_measurements (
	id SERIAL,
	entry_id INTEGER NOT NULL,
	flow FLOAT NOT NULL,
	direction TEXT CHECK (direction IN ('cw', 'ccw')) NOT NULL,
	time float NOT NULL,
	PRIMARY KEY (id, time)
);

CREATE TABLE IF NOT EXISTS rotary_measurements (
	id SERIAL,
	entry_id INTEGER NOT NULL,
	speed FLOAT NOT NULL,
	direction TEXT CHECK (direction IN ('cw', 'ccw')) NOT NULL,
	time float NOT NULL,
	PRIMARY KEY (id, time)
);

CREATE TABLE IF NOT EXISTS peristaltic_calibrations (
	id SERIAL PRIMARY KEY,
	duration INT NOT NULL,
	low_rpm INT NOT NULL,
	high_rpm INT NOT NULL,
	low_rpm_volume FLOAT NOT NULL,
	high_rpm_volume FLOAT NOT NULL,
	slope FLOAT NOT NULL,
	name VARCHAR(255) NOT NULL,
	diameter FLOAT
);

CREATE TABLE IF NOT EXISTS tube_configurations (
	id SERIAL PRIMARY KEY,
	name VARCHAR(255) UNIQUE NOT NULL,
	diameter FLOAT NOT NULL,
	flow_rate FLOAT NOT NULL,
	preset BOOLEAN NOT NULL
);

INSERT INTO tube_configurations (name, diameter, flow_rate, preset) VALUES ('0.76mm Tube', 0.76, 0.072683715, TRUE) ON CONFLICT DO NOTHING;
INSERT INTO tube_configurations (name, diameter, flow_rate, preset) VALUES ('1.0mm Tube', 1.0, 0.125837456, TRUE) ON CONFLICT DO NOTHING;
INSERT INTO tube_configurations (name, diameter, flow_rate, preset) VALUES ('1.42mm Tube', 1.42, 0.253738647, TRUE) ON CONFLICT DO NOTHING;
INSERT INTO tube_configurations (name, diameter, flow_rate, preset) VALUES ('1.50mm Tube', 1.50, 0.283134276, TRUE) ON CONFLICT DO NOTHING;
INSERT INTO tube_configurations (name, diameter, flow_rate, preset) VALUES ('1.52mm Tube', 1.52, 0.290734859, TRUE) ON CONFLICT DO NOTHING;
INSERT INTO tube_configurations (name, diameter, flow_rate, preset) VALUES ('2.00mm Tube', 2.00, 0.503349824, TRUE) ON CONFLICT DO NOTHING;

-- Add constraints
ALTER TABLE tilt_entry_table DROP CONSTRAINT IF EXISTS unique_tilt_entry_name;
ALTER TABLE tilt_entry_table ADD CONSTRAINT unique_tilt_entry_name UNIQUE (name);
ALTER TABLE tilt_entry_table ADD CONSTRAINT fk_tilt_scenario_id FOREIGN KEY (tilt_scenario_id) REFERENCES tilt_scenarios(id);

ALTER TABLE tilt_scenarios DROP CONSTRAINT IF EXISTS unique_scenario_name;
CREATE UNIQUE INDEX IF NOT EXISTS unique_active_tilt_scenario_name
    ON tilt_scenarios (name)
    WHERE is_active = TRUE;

ALTER TABLE tilt_measurements ADD CONSTRAINT fk_tilt_entry_id FOREIGN KEY (entry_id) REFERENCES tilt_entry_table(id);

ALTER TABLE rotation_entry_table DROP CONSTRAINT IF EXISTS unique_rotary_entry_name;
ALTER TABLE rotation_entry_table ADD CONSTRAINT unique_rotary_entry_name UNIQUE (name);
ALTER TABLE rotation_entry_table ADD CONSTRAINT fk_rotary_scenario_id FOREIGN KEY (rotary_scenario_id) REFERENCES rotary_scenarios(id);

ALTER TABLE rotary_scenarios DROP CONSTRAINT IF EXISTS unique_scenario_name;
CREATE UNIQUE INDEX IF NOT EXISTS unique_active_rotary_scenario_name
    ON rotary_scenarios (name)
    WHERE is_active = TRUE;

ALTER TABLE rotary_measurements ADD CONSTRAINT fk_rotary_entry_id FOREIGN KEY (entry_id) REFERENCES rotation_entry_table(id);

ALTER TABLE peristaltic_entry_table DROP CONSTRAINT IF EXISTS unique_peristaltic_entry_name;
ALTER TABLE peristaltic_entry_table ADD CONSTRAINT unique_peristaltic_entry_name UNIQUE (name);
ALTER TABLE peristaltic_entry_table ADD CONSTRAINT fk_peristaltic_scenario_id FOREIGN KEY (peristaltic_scenario_id) REFERENCES peristaltic_scenarios(id);

ALTER TABLE peristaltic_scenarios DROP CONSTRAINT IF EXISTS unique_scenario_name;
CREATE UNIQUE INDEX IF NOT EXISTS unique_active_peristaltic_scenario_name
    ON peristaltic_scenarios (name)
    WHERE is_active = TRUE;

ALTER TABLE peristaltic_measurements ADD CONSTRAINT fk_peristaltic_entry_id FOREIGN KEY (entry_id) REFERENCES peristaltic_entry_table(id);


SELECT create_hypertable('tilt_measurements', 'time', if_not_exists => TRUE);
SELECT create_hypertable('rotary_measurements', 'time', if_not_exists => TRUE);
SELECT create_hypertable('peristaltic_measurements', 'time', if_not_exists => TRUE);
