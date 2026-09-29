"""Tilt Motor Database Operations."""

from typing import Any, Dict, List, Optional

from app.database.database import db

# ---------------------------------------------------------
# Tilt scenarios
# ---------------------------------------------------------


def get_tilt_scenarios() -> List[Dict[str, Any]]:
    """Get all tilt scenarios from database."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, movement_mode, frequency,
                        microstepping, min_tilt, max_tilt, move_duration, repetitions, standstill_duration_left, standstill_duration_horizontal, standstill_duration_right, end_position
                    FROM tilt_scenarios WHERE is_active = TRUE
                    ORDER BY name
                """,
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise


def create_tilt_scenario(scenario_data: Dict[str, Any]) -> int:
    """Create a new tilt scenario and return its ID."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tilt_scenarios
                    (name, movement_mode, frequency, microstepping, min_tilt, max_tilt, move_duration, repetitions, standstill_duration_left, standstill_duration_horizontal, standstill_duration_right, end_position)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        scenario_data["name"],
                        scenario_data.get("movement_mode", "constant"),
                        scenario_data.get("frequency"),
                        scenario_data.get("microstepping"),
                        scenario_data.get("min_tilt"),
                        scenario_data.get("max_tilt"),
                        scenario_data.get("move_duration"),
                        scenario_data.get("repetitions"),
                        scenario_data.get("standstill_duration_left"),
                        scenario_data.get("standstill_duration_horizontal"),
                        scenario_data.get("standstill_duration_right"),
                        scenario_data.get("end_position"),
                    ),
                )
                result = cur.fetchone()  # Move inside cursor context
                conn.commit()
                return result["id"]
        except Exception:
            conn.rollback()
            raise


def update_tilt_scenario(scenario_id: int, scenario_data: Dict[str, Any]) -> bool:
    """Update a tilt scenario."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tilt_scenarios SET name = %s, movement_mode = %s, frequency = %s,
                            microstepping = %s, min_tilt = %s, max_tilt = %s, move_duration = %s, repetitions = %s,
                            standstill_duration_left = %s, standstill_duration_horizontal = %s, standstill_duration_right = %s, end_position = %s
                            WHERE id = %s
                            """,
                    (
                        scenario_data["name"],
                        scenario_data.get("movement_mode", "constant"),
                        scenario_data.get("frequency"),
                        scenario_data.get("microstepping"),
                        scenario_data.get("min_tilt"),
                        scenario_data.get("max_tilt"),
                        scenario_data.get("move_duration"),
                        scenario_data.get("repetitions"),
                        scenario_data.get("standstill_duration_left"),
                        scenario_data.get("standstill_duration_horizontal"),
                        scenario_data.get("standstill_duration_right"),
                        scenario_data.get("end_position"),
                        scenario_id,
                    ),
                )
                rowcount = cur.rowcount  # Capture before cursor closes
            conn.commit()
            return rowcount > 0  # Use captured value
        except Exception:
            conn.rollback()
            raise


def delete_tilt_scenario(scenario_id: str) -> bool:
    """Delete a tilt scenario."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tilt_scenarios SET is_active = FALSE WHERE id = %s",
                    (scenario_id,),
                )
                rowcount = cur.rowcount  # Capture before cursor closes
            conn.commit()
            return rowcount > 0  # Use captured value
        except Exception:
            conn.rollback()
            raise


def get_tilt_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    """Get a single tilt scenario by ID."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, movement_mode, frequency,
                           microstepping, min_tilt, max_tilt, move_duration, repetitions, standstill_duration_left, standstill_duration_horizontal, standstill_duration_right, end_position
                    FROM tilt_scenarios WHERE id = %s
                """,
                    (scenario_id,),  # Add missing parameter
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------
# Entry operations
# ---------------------------------------------------------


def create_entry(name: str, tilt_scenario_id: int, scenario_name: str) -> str:
    """Create a new entry and return its ID."""
    from datetime import datetime

    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tilt_entry_table (name, tilt_scenario_id, scenario_name, measurement_timestamp)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """,
                    (name, tilt_scenario_id, scenario_name, datetime.now()),
                )
                result = cur.fetchone()
                conn.commit()
                return int(result["id"])
        except Exception:
            conn.rollback()
            raise


def get_entry(entry_id: str) -> Optional[Dict[str, Any]]:
    """Get an entry by ID."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, measurement_timestamp, tilt_scenario_id, scenario_name
                    FROM tilt_entry_table
                    WHERE id = %s
                """,
                    (entry_id,),
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception:
            conn.rollback()
            raise


def get_entries() -> List[Dict[str, Any]]:
    """Get all entries."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, measurement_timestamp, tilt_scenario_id, scenario_name
                    FROM tilt_entry_table
                    ORDER BY measurement_timestamp DESC
                """,
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------
# Measurements
# ---------------------------------------------------------


def create_tilt_measurement(measurement_data: Dict[str, Any]) -> str:
    """Create a new tilt measurement and return its ID."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tilt_measurements
                    (entry_id, angle, state, time)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        measurement_data["entry_id"],
                        measurement_data["angle"],
                        measurement_data["state"],
                        measurement_data["time"],
                    ),
                )
                result = cur.fetchone()
                conn.commit()
                return str(result["id"])
        except Exception:
            conn.rollback()
            raise


def create_tilt_measurements_batch(measurements: List[Dict[str, Any]]) -> int:
    """Create multiple tilt measurements in a single batch insert."""
    if not measurements:
        return 0
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                values = [
                    (
                        m["entry_id"],
                        m["angle"],
                        m["state"],
                        m["time"],
                    )
                    for m in measurements
                ]
                cur.executemany(
                    """
                    INSERT INTO tilt_measurements
                    (entry_id, angle, state, time)
                    VALUES (%s, %s, %s, %s)
                """,
                    values,
                )
                conn.commit()
                return cur.rowcount
        except Exception:
            conn.rollback()
            raise


def get_tilt_measurements(
    entry_id: Optional[str] = None,
    tilt_scenario_id: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Get tilt measurements with optional filters."""
    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                query = """
                SELECT id, entry_id, angle, state, time
                FROM (
                    SELECT id, entry_id, angle, state, time
                    FROM tilt_measurements
                    WHERE 1=1
                """
                params = []

                if entry_id:
                    query += " AND entry_id = %s"
                    params.append(entry_id)

                query += """
                        ORDER BY time DESC
                        LIMIT %s
                    ) AS recent_measurements
                    ORDER BY time ASC
                """
                params.append(limit)

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise
