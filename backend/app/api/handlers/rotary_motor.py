import asyncio
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict

from app.api.handlers.postep256_handler import postep256_handler
from app.asyncio_loop import get_event_loop
from app.database.rotary_motor_handler import (
    create_entry,
    create_rotary_measurements_batch,
    create_rotary_scenario,
    delete_rotary_scenario,
    get_entries,
    get_rotary_measurements,
    get_rotary_scenarios,
    update_rotary_scenario,
)
from app.models import MotorStatus, Movement, RotationScenario
from app.websocket_manager import manager


class RotaryMotorHandler:
    """Handler for the Rotary PoStep motor."""

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def __init__(self):
        """Init function for the handler."""
        self._postep = None
        self._motor_status = MotorStatus.IDLE
        self._is_moving = False
        self._position_deg = 0  # in degrees
        self._max_speed = 1000
        self._max_acceleration = 70000
        self._max_deceleration = 70000
        self._initialized = False
        self._rotate_motor_task: threading.Thread = None
        self._rotate_motor_running = False
        self._rotate_motor_start_time = 0
        self._rotate_motor_paused = False
        self._movement_start_time = 0
        self._pause_pressed = False
        self._movement_stopped_time = 0
        self._movement_remaining_time = 0
        self._current_speed = 0
        self._movement_speed = 0
        self._resume_pressed = False
        self._stop_pressed = False
        self._current_direction = "cw"
        self._prev_pause_state = False
        self._measurement_queue: Deque[Dict[str, Any]] = deque()
        self._queue_lock = threading.Lock()
        self._current_entry_id: int = None
        self._save_interval = 0.5  # Save queue to DB every 0.5 second
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
            # self._postep.set_driver_settings(microstep=2)

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
            raise Exception(f"Error initializing Rotary motor: {e}")

    # ---------------------------------------------------------
    # Internal helpers (websocket, speed ramps, measurement queue)
    # ---------------------------------------------------------

    def _submit_async(self, coro):
        try:
            loop = get_event_loop()
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            print(f"Async submission error: {e}")

    def _send_rotate_stopped_websocket(self):
        """Send a rotate stopped update to the WebSocket."""
        try:
            self._submit_async(manager.send_rotate_stopped())
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")

    def _set_requested_speed(self, speed, direction, prev_direction="cw"):
        """Set the requested speed for the motor."""
        if prev_direction != direction and self._current_speed > 0:
            self._lower_speed_gradually(self._current_speed, sleep_when_stopped=False)

        if speed < self._current_speed and prev_direction == direction:
            for i in range(int(self._movement_speed), int(speed), -5):
                self._add_to_measurement_queue(
                    entry_id=self._current_entry_id,
                    speed=i / 100,
                    direction=direction,
                    time=time.time() - self._rotate_motor_start_time,
                )
                if self._stop_pressed or self._pause_pressed:
                    self._lower_speed_gradually(i, direction)
                    self._postep.run_sleep(False)

                    break
                self._postep.set_requested_speed(i, direction)
                self._current_speed = i
                time.sleep(0.05)
        elif (
            speed > self._current_speed
            and self._current_speed > 0
            and prev_direction == direction
        ):
            for i in range(self._movement_speed, int(speed), 5):
                self._add_to_measurement_queue(
                    entry_id=self._current_entry_id,
                    speed=i / 100,
                    direction=direction,
                    time=time.time() - self._rotate_motor_start_time,
                )
                if self._stop_pressed or self._pause_pressed:
                    self._lower_speed_gradually(i, direction)
                    self._postep.run_sleep(False)
                    break
                self._postep.set_requested_speed(i, direction)
                self._current_speed = i
                time.sleep(0.05)
        else:
            if self._current_speed > 0:
                self._lower_speed_gradually(self._current_speed, prev_direction)
            for i in range(0, int(speed), 5):
                self._add_to_measurement_queue(
                    entry_id=self._current_entry_id,
                    speed=i / 100,
                    direction=direction,
                    time=time.time() - self._rotate_motor_start_time,
                )
                if self._stop_pressed or self._pause_pressed:
                    self._lower_speed_gradually(i, direction)
                    self._postep.run_sleep(False)
                    break
                self._postep.set_requested_speed(i, direction)
                self._current_speed = i
                time.sleep(0.05)
        if not self._stop_pressed:
            self._postep.set_requested_speed(int(speed), direction)
            self._current_speed = int(speed)
        return

    def _lower_speed_gradually(self, speed: int, sleep_when_stopped: bool = True):
        """Lower the speed gradually."""
        for i in range(speed, 0, -5):
            self._add_to_measurement_queue(
                entry_id=self._current_entry_id,
                speed=i / 100,
                direction=self._current_direction,
                time=time.time() - self._rotate_motor_start_time,
            )
            self._postep.set_requested_speed(i, self._current_direction)
            self._current_speed = i
            time.sleep(0.05)
        self._postep.set_requested_speed(0, self._current_direction)
        if sleep_when_stopped:
            self._postep.set_run(False)
        self._current_speed = 0

    def _rotate_motor_thread(self, movements: list[Movement]):
        try:
            self._rotate_motor_start_time = time.time()
            movement_index = 0
            for movement in movements:
                self.send_rotate_movement_websocket(movement_index)
                movement_index += 1
                self._movement_speed = movement.rpm * 100
                self._movement_start_time = time.time()
                self._movement_remaining_time = 0
                self._set_requested_speed(
                    self._movement_speed, movement.direction, self._current_direction
                )
                self._current_direction = movement.direction

                while (
                    time.time() - self._movement_start_time < movement.duration
                    or movement.duration == 0
                ):
                    if self._stop_pressed:
                        break
                    if self._pause_pressed or self._rotate_motor_paused:
                        self._lower_speed_gradually(
                            self._current_speed, self._current_direction
                        )
                        self._postep.run_sleep(False)
                        while self._rotate_motor_paused:
                            if self._stop_pressed:
                                break
                            time.sleep(0.2)
                            self._add_to_measurement_queue(
                                entry_id=self._current_entry_id,
                                speed=0,
                                direction=self._current_direction,
                                time=time.time() - self._rotate_motor_start_time,
                            )
                            if self._resume_pressed:
                                self._postep.run_sleep(True)
                                time.sleep(0.05)
                                self._set_requested_speed(
                                    self._movement_speed,
                                    self._current_direction,
                                    self._current_direction,
                                )
                                if movement.duration > 0:
                                    movement.duration = (
                                        movement.duration
                                        - self._movement_remaining_time
                                    )
                                self._resume_pressed = False
                                self._pause_pressed = False
                                self._rotate_motor_paused = False
                                self._movement_start_time = time.time()
                                continue

                    stream_data = self._postep.read_stream()
                    if stream_data and "pos" in stream_data:
                        self._position_deg = stream_data["pos"]
                        if (
                            self._current_entry_id is not None
                            and self._current_speed > 0
                        ):
                            self._add_to_measurement_queue(
                                entry_id=self._current_entry_id,
                                speed=movement.rpm,
                                direction=self._current_direction,
                                time=time.time() - self._rotate_motor_start_time,
                            )

            self._lower_speed_gradually(self._current_speed, self._current_direction)
            self._postep.move_to_stop()
            self._postep.run_sleep(False)
            time.sleep(0.1)
            self._send_rotate_stopped_websocket()

            self._rotate_motor_running = False
            self._stop_pressed = False
            self._pause_pressed = False
            self._rotate_motor_paused = False
            self._resume_pressed = False
            self._is_moving = False
            self._motor_status = MotorStatus.IDLE
            self._rotate_motor_start_time = 0
            self.stop_motor()
        except Exception as e:
            print(f"Error in rotate_motor thread: {e}")
            raise e

    def _add_to_measurement_queue(
        self, entry_id: int, speed: int, direction: str, time: datetime
    ):
        """Add a measurement to the queue."""
        with self._queue_lock:
            self._measurement_queue.append(
                {
                    "entry_id": entry_id,
                    "speed": speed,
                    "direction": direction,
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
            create_rotary_measurements_batch(measurements_to_save)
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
        while self._is_moving:
            batch = self._save_measurements_batch()
            if batch:
                self.send_measurements_websocket(batch)
            time.sleep(self._save_interval)

        # Save any remaining measurements when stopping
        final_batch = self._save_measurements_batch()
        if final_batch:
            self.send_measurements_websocket(final_batch)

        self._current_entry_id = None

    def send_rotate_movement_websocket(self, movement: int):
        """Send a rotate movement update to the WebSocket."""
        try:
            self._submit_async(manager.send_rotate_movement(movement))
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")

    def send_measurements_websocket(self, measurements: list[Dict[str, Any]]):
        """Send measurements to the WebSocket."""
        try:
            self._submit_async(manager.send_rotate_measurements(measurements))
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")
        except Exception as e:
            print(f"Error sending WebSocket update: {e}")

    # ---------------------------------------------------------
    # Public motor control (rotate)
    # ---------------------------------------------------------

    def rotate_motor(
        self,
        entry_name: str,
        scenario_id: int,
        scenario_name: str,
        movements: list[Movement],
    ) -> bool:
        """Rotate motor from min to max in non-stop motion."""
        if self._is_moving:
            return False

        entry_id = create_entry(
            name=entry_name,
            rotary_scenario_id=scenario_id,
            scenario_name=scenario_name,
        )

        self._current_entry_id = entry_id
        self._postep.run_sleep(True)
        self._rotate_motor_running = True
        self._postep.get_driver_settings()
        self._postep.set_driver_settings(step_mode=2, microstep=2)
        time.sleep(0.1)
        self._is_moving = True
        self._motor_status = MotorStatus.MOVING
        self._rotate_motor_task = threading.Thread(
            target=self._rotate_motor_thread,
            args=(movements,),
            daemon=True,
        )
        self._stop_pressed = False
        self._rotate_motor_task.start()
        self._save_measurements_task = threading.Thread(
            target=self._handle_measurements_thread,
            args=(entry_id,),
            daemon=True,
        )
        self._save_measurements_task.start()
        return True

    def stop_rotate_motor(self):
        """Manually stop the rotate motor motion."""
        if (
            self._rotate_motor_running
            and self._rotate_motor_task
            and self._rotate_motor_task.is_alive()
        ):
            self._stop_pressed = True
            self._rotate_motor_task.join(timeout=3)
            self._is_moving = False
            self._motor_status = MotorStatus.IDLE
            self._rotate_motor_task = None
            if self._save_measurements_task:
                self._save_measurements_task.join(timeout=3)
                self._measurement_queue.clear()
                self._save_measurements_task = None

    def pause_rotate_motor(self):
        """Pause the rotate motor motion temporarily."""
        if (
            self._rotate_motor_running
            and self._rotate_motor_task
            and self._rotate_motor_task.is_alive()
            and not self._rotate_motor_paused
        ):
            self._movement_remaining_time = time.time() - self._movement_start_time
            self._rotate_motor_paused = True
            self._pause_pressed = True
            self._movement_stopped_time = time.time()
            self._resume_pressed = False

    def resume_rotate_motor(self, movement: int):
        """Resume the rotate motor motion from where it was paused."""
        if (
            self._rotate_motor_running
            and self._rotate_motor_task
            and self._rotate_motor_task.is_alive()
            and self._rotate_motor_paused
        ):
            self._pause_pressed = False
            self._postep.run_sleep(True)
            self._resume_pressed = True
            self._pause_pressed = False
            self._rotate_motor_paused = False

    # ---------------------------------------------------------
    # Movement state helpers + status
    # ---------------------------------------------------------

    def stop_motor(self) -> bool:
        """Stop motor movement using PoStep256 USB."""
        if not self._is_moving:
            return True

        if self._postep.device is None:
            return False

        try:
            self._postep.move_to_stop()
            self._postep.run_sleep(False)
        except Exception as e:
            print(f"Error stopping rotary motor: {e}")
            return False

        self._is_moving = False
        self._motor_status = MotorStatus.IDLE

        return True

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
    def get_entries(self) -> list[dict]:
        """Get list of entries."""
        return get_entries()

    def get_measurements(self, entry_id: str, limit: int = 1000) -> list[dict]:
        """Get list of measurements."""
        return get_rotary_measurements(entry_id=entry_id, limit=limit)

    def get_rotation_scenarios(self) -> list[dict]:
        """Get list of rotation scenarios."""
        return get_rotary_scenarios()

    def save_rotation_scenario(self, scenario: RotationScenario) -> int:
        """Save a rotation scenario."""
        scenario_id = create_rotary_scenario(scenario)
        return scenario_id

    def update_rotation_scenario(
        self, scenario_id: int, scenario: RotationScenario
    ) -> bool:
        """Update a rotation scenario."""
        return update_rotary_scenario(
            scenario_id=scenario_id,
            scenario=scenario,
        )

    def remove_rotation_scenario(self, scenario_id: str) -> bool:
        """Remove a rotation scenario."""
        delete_rotary_scenario(scenario_id=scenario_id)
        return True

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def cleanup(self):
        """Cleanup resources."""
        if self._postep:
            try:
                # self.move_to_deg(0)
                self.stop_motor()
                self._postep.set_run(False)
            except Exception as e:
                print(f"Error cleaning up rotary motor: {e}")
        print("Rotary motor cleanup completed")


rotary_motor_handler = RotaryMotorHandler()
