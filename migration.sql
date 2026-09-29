-- Tilt scenarios: add movement mode (constant / sinusoidal) and frequency.
-- Sinusoidal scenarios store frequency, min_tilt, max_tilt and repetitions,
-- so the other constant-movement fields become nullable. Existing scenarios
-- are migrated as 'constant'.
-- Safe to run multiple times.
BEGIN;

ALTER TABLE tilt_scenarios ADD COLUMN IF NOT EXISTS movement_mode VARCHAR(20) NOT NULL DEFAULT 'constant';
ALTER TABLE tilt_scenarios ALTER COLUMN movement_mode SET DEFAULT 'constant';
ALTER TABLE tilt_scenarios ADD COLUMN IF NOT EXISTS frequency FLOAT;

ALTER TABLE tilt_scenarios
	ALTER COLUMN microstepping DROP NOT NULL,
	ALTER COLUMN min_tilt DROP NOT NULL,
	ALTER COLUMN max_tilt DROP NOT NULL,
	ALTER COLUMN move_duration DROP NOT NULL,
	ALTER COLUMN repetitions DROP NOT NULL,
	ALTER COLUMN end_position DROP NOT NULL,
	ALTER COLUMN standstill_duration_left DROP NOT NULL,
	ALTER COLUMN standstill_duration_horizontal DROP NOT NULL,
	ALTER COLUMN standstill_duration_right DROP NOT NULL;

ALTER TABLE tilt_scenarios DROP CONSTRAINT IF EXISTS tilt_scenarios_movement_mode_check;
ALTER TABLE tilt_scenarios ADD CONSTRAINT tilt_scenarios_movement_mode_check
	CHECK (movement_mode IN ('constant', 'sinusoidal'));

ALTER TABLE tilt_scenarios DROP CONSTRAINT IF EXISTS tilt_scenarios_frequency_check;
ALTER TABLE tilt_scenarios ADD CONSTRAINT tilt_scenarios_frequency_check
	CHECK (frequency > 0);

ALTER TABLE tilt_scenarios DROP CONSTRAINT IF EXISTS tilt_scenarios_mode_fields_check;

-- Sinusoidal scenarios saved before min/max tilt and repetitions were added
-- used +/-20 deg and 10 periods.
UPDATE tilt_scenarios
SET
	min_tilt = COALESCE(min_tilt, -20),
	max_tilt = COALESCE(max_tilt, 20),
	repetitions = COALESCE(repetitions, 10)
WHERE movement_mode = 'sinusoidal';

ALTER TABLE tilt_scenarios ADD CONSTRAINT tilt_scenarios_mode_fields_check CHECK (
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
);

COMMIT;
