import asyncio
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict
import csv
import os
import time
from app.api.handlers.postep256_handler import postep256_handler
from app.asyncio_loop import get_event_loop
from app.database.tilt_motor_handler import (
    create_entry,
    create_tilt_measurements_batch,
    create_tilt_scenario,
    delete_tilt_scenario,
    get_entries,
    get_tilt_measurements,
    get_tilt_scenario,
    get_tilt_scenarios,
    update_tilt_scenario,
)
from app.models import MotorStatus, MoveScenario
from app.websocket_manager import manager

STEPPER_STEP_ANGLE = 1.8
GEAR_RATIO = 50


class TiltMotorHandler:
    """Handler for the Tilt PoStep motor."""

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def __init__(self):
        """Init function for the handler."""
        self._postep = None
        self._motor_status = MotorStatus.IDLE
        self._is_moving = False
        self._max_position_deg = 2000000
        self._min_position_deg = -2000000
        self._position_deg = 0  # in degrees
        self._max_speed = 40000
        self._max_acceleration = 40000
        self._max_deceleration = 40000
        self._calculated_steps = 0
        self._initialized = False
        self._tilt_motor_task: threading.Thread = None
        self._tilt_motor_running = False
        self._tilt_motor_start_time = 0
        self._tilt_motor_paused = False
        self._pause_pressed = False
        self._resume_pressed = False
        self._stop_pressed = False
        self._prev_pause_state = False
        self._measurement_queue: Deque[Dict[str, Any]] = deque()
        self._queue_lock = threading.Lock()
        self._current_entry_id: int = None
        self._save_interval = 0.2  # Save queue to DB every 1 second
        self._save_measurements_task: threading.Thread = None

    def initialize(self):
        """Initialize motor hardware with PoStep256 USB."""
        try:
            # Initialize shared device if not already initialized
            if not postep256_handler.is_initialized():
                postep256_handler.initialize(
                    max_speed=self._max_speed,
                    max_accel=self._max_acceleration,
                    max_decel=self._max_deceleration,
                )

            # Get the shared postep instance
            self._postep = postep256_handler.get_postep()
            self._position_deg = postep256_handler.get_position()

            # Configure motor-specific settings
            # self._postep.set_driver_settings(step_mode=4)
            # self._postep.set_run(True)
            time.sleep(0.2)

            # Update position after settings
            try:
                stream_data = self._postep.read_stream()
                if stream_data and "pos" in stream_data:
                    self._position_deg = stream_data["pos"]
                    postep256_handler.update_position(self._position_deg)
            except Exception as e:
                print(f"Warning: Could not read position: {e}")

            self._initialized = True
        except Exception as e:
            self._motor_status = MotorStatus.ERROR
            self._initialized = False
            raise Exception(f"Error initializing Tilt motor: {e}")

    # ---------------------------------------------------------
    # Internal helpers (movement + websocket + measurement queue)
    # ---------------------------------------------------------
    def _submit_async(self, coro):
        try:
            loop = get_event_loop()
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            print(f"Async submission error: {e}")

    def _move_if_allowed(
        self, target_position, standstill_duration, move_duration
    ) -> bool:
        """Check if the motor can move to the target position and move to the position."""

        # Log every call
        csv_file = "motor_movements.csv"
        file_exists = os.path.isfile(csv_file)

        with open(csv_file, "a", newline="") as f:
            writer = csv.writer(f)

            # Write header only if the file is new
            if not file_exists:
                writer.writerow(
                    ["timestamp", "target_position", "standstill_duration", "move_duration"]
                )

            writer.writerow(
                [time.time(), target_position, standstill_duration, move_duration]
            )

        if self._tilt_motor_paused or not self._tilt_motor_running:
            return False

        if target_position == 0 and standstill_duration == 0:
            return True

        self.move_to_deg(target_position, move_duration + 10)
        time.sleep(standstill_duration)

        return True

    def _send_tilt_stopped_websocket(self):
        """Send a tilt stopped update to the WebSocket."""
        try:
            self._submit_async(manager.send_tilt_stopped())
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")

    def _tilt_motor_thread(
        self,
        angle,
        repetitions,
        min_tilt,
        max_tilt,
        move_duration,
        end_position,
        microstepping,
        standstill_duration_left,
        standstill_duration_horizontal,
        standstill_duration_right,
    ):
        try:
            positions = [min_tilt, 0, max_tilt]
            i = 1
            angle_diff = 20 / (angle)
            C = 90
            req_speed = (
                6 / move_duration * C * 2**microstepping * (angle_diff)
            ) / angle_diff  # 4000 is (test) found constant for time calculation
            self._postep.move_config(
                max_speed=int(req_speed),
                max_accel=int(20000),
                max_decel=int(5000),
                endsw=None,
            )
            self._postep.move_reset_to_zero()
            time.sleep(0.2)
            self._tilt_motor_start_time = time.time()
            self.move_to_deg(0)
            repeat = "repetitions"
            if repetitions == 0:
                repeat = "infinite"
            while self._tilt_motor_running and (
                i < repetitions or repeat == "infinite"
            ):
                self.send_repetitions_websocket(i)
                i += 1

                if not self._move_if_allowed(
                    max_tilt, standstill_duration_right, move_duration
                ):
                    break
                if not self._move_if_allowed(
                    0, standstill_duration_horizontal, move_duration
                ):
                    break
                if not self._move_if_allowed(
                    min_tilt, standstill_duration_left, move_duration
                ):
                    break
                if not self._move_if_allowed(
                    0, standstill_duration_horizontal, move_duration
                ):
                    break
                if repeat == "repetitions" and i > repetitions:
                    self.send_repetitions_websocket(i)
                    break
            if self._tilt_motor_running:
                self.move_to_deg(0)
                self.move_to_deg(positions[end_position])
            if self._save_measurements_task:
                self._save_measurements_task.join(timeout=3)
                self._save_measurements_task = None
            self._send_tilt_stopped_websocket()
            self._tilt_motor_running = False
            self._tilt_motor_start_time = 0
            self._is_moving = False
            self._motor_status = MotorStatus.IDLE
            self._postep.run_sleep(False)
        except Exception as e:
            print(f"Error in tilt_motor thread: {e}")

    def send_repetitions_websocket(self, repetitions: int):
        """Send measurements to the WebSocket."""
        try:
            self._submit_async(manager.send_repetitions(repetitions))
        except RuntimeError:
            print("Error sending repetitions to WebSocket")

    def _add_to_measurement_queue(
        self, entry_id: int, angle: float, state: str, time: datetime
    ):
        """Add a measurement to the queue."""
        with self._queue_lock:
            self._measurement_queue.append(
                {
                    "entry_id": entry_id,
                    "angle": angle,
                    "state": state,
                    "time": time,
                }
            )

    def _save_measurements_batch(self):
        """Save queued measurements to database in batch and return the batch."""
        measurements_to_save: list[Dict[str, Any]] = []
        with self._queue_lock:
            if self._measurement_queue:
                measurements_to_save = list(self._measurement_queue)
                self._measurement_queue.clear()

        if not measurements_to_save:
            return []

        try:
            create_tilt_measurements_batch(measurements_to_save)
        except Exception as e:
            print(f"Error saving measurements batch: {e}")
            # Re-add measurements to queue on error
            with self._queue_lock:
                self._measurement_queue.extendleft(reversed(measurements_to_save))
            # On error we consider nothing was successfully sent
            return []

        return measurements_to_save

    def _handle_measurements_thread(self, entry_id: int):
        """Thread that periodically saves queued measurements to database."""
        self._current_entry_id = entry_id
        while self._tilt_motor_running:
            batch = self._save_measurements_batch()
            if batch:
                self.send_measurements_websocket(batch)
            time.sleep(self._save_interval)

        # Save any remaining measurements when stopping
        final_batch = self._save_measurements_batch()
        if final_batch:
            self.send_measurements_websocket(final_batch)

        self._current_entry_id = None

    def send_measurements_websocket(self, measurements: list[Dict[str, Any]]):
        """Send measurements to the WebSocket."""
        try:
            self._submit_async(manager.send_measurements(measurements))
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")

    # ---------------------------------------------------------
    # Public motor control (tilt, move, home)
    # ---------------------------------------------------------

    def tilt_motor(
        self,
        entry_name: str,
        scenario_id: int,
        scenario_name: str,
        microstepping: int,
        repetitions: int,
        min_tilt: int,
        max_tilt: int,
        end_position: int = 1,
        move_duration: float = 1,
        standstill_duration_left: int = 0.2,
        standstill_duration_horizontal: int = 0.2,
        standstill_duration_right: int = 0.2,
    ) -> bool:
        """Tilt motor from min to max in non-stop motion."""
        if min_tilt < self._min_position_deg or max_tilt > self._max_position_deg:
            print("Targets exceed the maximum tilt options.")
            return False

        if self._is_moving:
            print("Tilt motor is already moving.")
            return False
        self._postep.get_driver_settings()
        self._postep.set_driver_settings(step_mode=4, microstep=microstepping)
        time.sleep(0.1)
        entry_id = create_entry(
            name=entry_name,
            tilt_scenario_id=scenario_id,
            scenario_name=scenario_name,
        )

        self._current_entry_id = entry_id
        self._postep.set_run(True)
        time.sleep(0.1)
        self._tilt_motor_running = True
        self._tilt_motor_paused = False
        self._is_moving = True
        self._motor_status = MotorStatus.MOVING
        self._calculated_steps = int(1 / (STEPPER_STEP_ANGLE / (2**microstepping)))
        min_deg = min_tilt * self._calculated_steps * GEAR_RATIO
        max_deg = max_tilt * self._calculated_steps * GEAR_RATIO
        self._tilt_motor_task = threading.Thread(
            target=self._tilt_motor_thread,
            args=(
                max_tilt,
                repetitions,
                min_deg,
                max_deg,
                move_duration,
                end_position,
                microstepping,
                standstill_duration_left,
                standstill_duration_horizontal,
                standstill_duration_right,
            ),
            daemon=True,
        )
        self._tilt_motor_task.start()
        self._save_measurements_task = threading.Thread(
            target=self._handle_measurements_thread,
            args=(entry_id,),
            daemon=True,
        )
        self._save_measurements_task.start()
        return True

    def stop_tilt_motor(self):
        """Manually stop the tilt motor motion."""
        if (
            self._tilt_motor_running
            and self._tilt_motor_task
            and self._tilt_motor_task.is_alive()
        ):
            self._stop_pressed = True
            self._is_moving = False
            self._motor_status = MotorStatus.IDLE
            self._postep.run_sleep(False)
            self._tilt_motor_running = False  # Stop the save thread
            self._tilt_motor_task.join(timeout=3)
            self._tilt_motor_task = None

    def pause_tilt_motor(self):
        """Pause the tilt motor motion temporarily."""
        if (
            self._tilt_motor_running
            and self._tilt_motor_task
            and self._tilt_motor_task.is_alive()
            and not self._tilt_motor_paused
        ):
            self._pause_pressed = True
            self._resume_pressed = False

    def resume_tilt_motor(self):
        """Resume the tilt motor motion from where it was paused."""
        if (
            self._tilt_motor_running
            and self._tilt_motor_task
            and self._tilt_motor_task.is_alive()
            and self._tilt_motor_paused
        ):
            self._resume_pressed = True
            self._pause_pressed = False
            self._tilt_motor_paused = False
            self._is_moving = True
            self._motor_status = MotorStatus.MOVING

    def move_to_deg(self, target_position: int, timeout: int = 10) -> bool:
        """Move motor to a specified degree value."""
        if self._motor_status == MotorStatus.ERROR:
            self._initialized = False
            print("There is an error with the tilt motor.")
            return False

        # Validate position limits
        if (
            target_position < self._min_position_deg
            or target_position > self._max_position_deg
        ):
            raise ValueError(
                f"Target position {target_position} out of range [{self._min_position_deg}, {self._max_position_deg}]"
            )

        try:
            self._is_moving = True
            self._motor_status = MotorStatus.MOVING
            self._postep.move_to(int(target_position))
            start_time = time.time()

            while True:
                stream_data = self._postep.read_stream()
                if self._stop_pressed:
                    self._set_stop_movement_flags()
                    break

                if self._pause_pressed and not self._prev_pause_state:
                    self._postep.move_to_stop()
                    self._set_pause_movement_flags()
                    timeout = 1000000

                if self._resume_pressed and self._prev_pause_state:
                    self._postep.move_to(target_position)
                    start_time = time.time()
                    self._set_resume_movement_flags()

                if stream_data and "pos" in stream_data:
                    self._position_deg = stream_data["pos"]
                    if self._current_entry_id is not None:
                        self._add_to_measurement_queue(
                            entry_id=self._current_entry_id,
                            angle=float(self._position_deg)
                            / self._calculated_steps
                            / 50,
                            time=time.time() - self._tilt_motor_start_time,
                            state=self._motor_status.value,
                        )
                    if self._position_deg == target_position:
                        break
                if (
                    not self._pause_pressed
                    and not self._stop_pressed
                    and time.time() - start_time > timeout
                ):
                    self._postep.move_to_stop()
                    stream_data = self._postep.read_stream()
                    if stream_data and "pos" in stream_data:
                        self._position_deg = stream_data["pos"]

                        self._new_data_available = True
                    raise TimeoutError(
                        "Failed to reach target position within timeout."
                    )
                time.sleep(0.01)

        except Exception as e:
            self._is_moving = False
            print(f"Error moving tilt motor: {e}")
            return False

        return True

    def stop_motor(self) -> bool:
        """Stop motor movement using PoStep256 USB."""
        if not self._is_moving:
            return True

        if self._postep.device is None:
            return False

        try:
            self._postep.move_to_stop()
        except Exception as e:
            print(f"Error stopping tilt motor: {e}")
            return False

        self._is_moving = False
        self._motor_status = MotorStatus.IDLE

        return True

    def move_to_home(self) -> bool:
        """Move motor to home."""
        # if self._position_deg < 0:
        #    direction = "ccw"
        # if self._position_deg != 0:
        self._postep.run_sleep(True)
        self._postep.get_driver_settings()
        self._postep.set_driver_settings(step_mode=2, microstep=2)
        time.sleep(0.2)
        self._postep.set_requested_speed(400, "ccw")
        while True:
            stream_data = self._postep.read_stream()
            if stream_data and "endswitch" in stream_data:
                if not stream_data["endswitch"]:
                    time.sleep(0.05)
                    self._postep.set_requested_speed(0)

                    break
        self._postep.move_reset_to_zero()
        time.sleep(0.2)
        self._postep.set_requested_speed(400, "cw")
        time.sleep(0.916)
        self._postep.set_requested_speed(0)
        self._postep.run_sleep(False)
        self._postep.move_reset_to_zero()
        self._position_deg = 0
        time.sleep(0.1)
        self._is_moving = False

        self._motor_status = MotorStatus.IDLE
        return True

    # ---------------------------------------------------------
    # Movement state helpers + status
    # ---------------------------------------------------------

    def _set_stop_movement_flags(self):
        """Set flags to stop motor movement."""
        self._is_moving = False
        self._stop_pressed = False
        self._pause_pressed = False
        self._resume_pressed = False
        self._prev_pause_state = False
        self._tilt_motor_paused = False
        self._tilt_motor_running = False

    def _set_pause_movement_flags(self):
        """Set flags to pause motor movement."""
        self._prev_pause_state = True
        self._tilt_motor_paused = True
        self._pause_pressed = False

    def _set_resume_movement_flags(self):
        """Set flags to resume motor movement."""
        self._prev_pause_state = False
        self._tilt_motor_paused = False

    def get_status(self) -> dict:
        """Get current motor status."""
        return {
            "status": self._motor_status.value,
            "position": self._position_deg,
            "is_moving": self._is_moving,
            "initialized": self._initialized,
        }

    # ---------------------------------------------------------
    # Scenario DB wrappers
    # ---------------------------------------------------------
    def create_entry(self, name: str, tilt_scenario_id: int, scenario_name: str) -> int:
        """Create a new entry and return its ID."""
        return create_entry(name, tilt_scenario_id, scenario_name)

    def get_entries(self) -> list[dict]:
        """Get list of entries."""
        return get_entries()

    def get_measurements(self, entry_id: str, limit: int = 1000) -> list[dict]:
        """Get list of measurements."""
        return get_tilt_measurements(entry_id=entry_id, limit=limit)

    def get_move_scenarios(self) -> list[dict]:
        """Get list of move scenarios."""
        return get_tilt_scenarios()

    def get_move_scenario(self, scenario_id: int) -> MoveScenario:
        """Get a move scenario by ID."""
        return get_tilt_scenario(scenario_id=scenario_id)

    def update_move_scenario(self, scenario_id: int, scenario: MoveScenario) -> bool:
        """Update a move scenario."""
        return update_tilt_scenario(
            scenario_id=scenario_id,
            scenario_data=scenario.model_dump(exclude_none=True),
        )

    def save_move_scenario(self, scenario: MoveScenario) -> bool:
        """Save a move scenario."""
        scenario_id = create_tilt_scenario(scenario.model_dump(exclude_none=True))
        return scenario_id

    def remove_move_scenario(self, scenario_id: str) -> bool:
        """Remove a move scenario."""
        delete_tilt_scenario(scenario_id=scenario_id)
        return True

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def cleanup(self):
        """Cleanup resources."""
        if self._is_moving:
            self.stop_motor()
        if self._postep:
            try:
                self.move_to_deg(0)
                self._postep.set_run(False)
            except Exception as e:
                print(f"Error cleaning up tilt motor: {e}")
        print("Tilt motor cleanup completed")


tilt_motor_handler = TiltMotorHandler()
