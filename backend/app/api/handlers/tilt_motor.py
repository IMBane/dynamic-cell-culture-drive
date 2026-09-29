import asyncio
import math
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict

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
SINUSOIDAL_STEP_MODE = 2
SINUSOIDAL_MICROSTEP = 2
SINUSOIDAL_CONTROL_INTERVAL = 0.02  # s between speed commands

# Sinusoidal mode: position follows a sine wave that starts in the middle and
# goes to max_tilt on the positive half waves and to min_tilt on the negative
# half waves. The first quarter period is ramped in, so the initial move starts
# and ends at zero speed before the regular direction changes begin. The last
# quarter period is faded out, so the motor ends in the middle with zero speed.
# Hard limit of the output angle (+/- deg). min_tilt and max_tilt must be
# within this.
SINUSOIDAL_MAX_ANGLE_DEG = 20.0
# Speed units (PoStep requested speed * s) per output degree in speed mode.
# Theoretical value is 2**microstep / 1.8 * gear ratio = 111.1, but the real
# motion is larger. Calibrate: run a test, measure the real peak angle and set
#   SINUSOIDAL_STEPS_PER_DEG = current value * commanded peak / measured peak
# (the commanded peaks are printed per cycle as "estimated peaks").
# Calibrated at 0.10 Hz: commanded 4.5 deg -> measured ~44 deg,
#   111.1 * 4.5 / 44 = 11.4
SINUSOIDAL_STEPS_PER_DEG = 11.4
# The startup transfer uses half a period. Its cosine position profile reaches
# the first peak at 80% of the normal sine-wave peak speed. The final quarter
# period fades the motor out from the last peak back to the middle.
SINUSOIDAL_RAMP_PERIODS = 0.8
SINUSOIDAL_FADE_PERIODS = 0.25
SINUSOIDAL_MIN_FREQUENCY = 0.01  # Hz
SINUSOIDAL_MAX_FREQUENCY = 0.5  # Hz
SINUSOIDAL_KP = 2.0  # 1/s, correction gain for USB timing jitter
# Set to -1 if a "cw" speed command decreases the reported position.
SINUSOIDAL_CW_SIGN = 1
# Commanded speed is never allowed above this factor x the sine peak speed.
SINUSOIDAL_MAX_SPEED_FACTOR = 1.2


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
        self._max_acceleration = 10000
        self._max_deceleration = 10000
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
        self._save_interval = 0.5  # Save queue to DB every 1 second
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
            print("Trying to initialize the tilt motor")
            self._postep = postep256_handler.get_postep()
            print(self._postep)
            self._position_deg = postep256_handler.get_position()

            # Configure motor-specific settings
            self._postep.set_driver_settings(step_mode=4)
            self._postep.set_run(True)
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
        if self._tilt_motor_paused or not self._tilt_motor_running:
            return False
        if target_position == 0 and standstill_duration == 0:
            return True
        print(
            f"Moving to {target_position} for {move_duration + 10} seconds with standstill duration {standstill_duration}"
        )
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
                if repeat == "repetitions" and i >= repetitions:
                    self.send_repetitions_websocket(i)
                    break
            if self._tilt_motor_running:
                self.move_to_deg(0)
                self.move_to_deg(positions[end_position])
            # Stop the save thread first so it flushes the last batch and exits.
            self._tilt_motor_running = False
            if self._save_measurements_task:
                self._save_measurements_task.join(timeout=3)
                self._save_measurements_task = None
            self._send_tilt_stopped_websocket()
            self._tilt_motor_start_time = 0
            self._is_moving = False
            self._motor_status = MotorStatus.IDLE
            self._postep.run_sleep(False)

        except Exception as e:
            print(f"Error in tilt_motor thread: {e}")

    def _queue_tilt_angle(self, angle_deg: float):
        """Queue a tilt angle (deg) for the DB and the live chart."""
        if self._current_entry_id is None:
            return
        self._add_to_measurement_queue(
            entry_id=self._current_entry_id,
            angle=round(angle_deg, 3),
            time=time.time() - self._tilt_motor_start_time,
            state=self._motor_status.value,
        )

    def _sinusoidal_tilt_motor_thread(
        self, frequency: float, min_tilt: float, max_tilt: float, repetitions: int
    ):
        """Follow a sine position reference with the given frequency (Hz).

        Positive half waves go to max_tilt, negative ones to min_tilt (deg).
        repetitions is the number of full periods, 0 means infinite.
        """
        steps_per_deg = SINUSOIDAL_STEPS_PER_DEG
        upper_limit = max_tilt * steps_per_deg
        lower_limit = min_tilt * steps_per_deg
        omega = 2 * math.pi * frequency
        max_speed = SINUSOIDAL_MAX_SPEED_FACTOR * max(upper_limit, -lower_limit) * omega
        period = 1 / frequency
        ramp = SINUSOIDAL_RAMP_PERIODS * period
        fade = SINUSOIDAL_FADE_PERIODS * period
        total_duration = (
            ramp + repetitions * period + fade if repetitions > 0 else math.inf
        )
        dt = SINUSOIDAL_CONTROL_INTERVAL

        def reference(t: float) -> float:
            # Smoothly accelerate and decelerate during the initial move from
            # the middle to the first positive peak. A half-period cosine
            # profile reaches the peak at half the normal sine-wave speed.
            if t < ramp:
                return upper_limit * 0.5 * (1 - math.cos(math.pi * t / ramp))

            # Begin the regular sine motion at its positive peak so position
            # and speed remain continuous with the startup transfer.
            s = math.cos(omega * (t - ramp))
            x = (upper_limit if s >= 0 else -lower_limit) * s
            # Smooth fade out at the end, so the motor stops in the middle.
            if t > total_duration - fade:
                x *= 0.5 * (1 - math.cos(math.pi * max(total_duration - t, 0) / fade))
            return x

        try:
            self._postep.set_driver_settings(
                step_mode=SINUSOIDAL_STEP_MODE,
                microstep=SINUSOIDAL_MICROSTEP,
            )
            self._tilt_motor_start_time = time.time()
            t0 = time.monotonic()
            paused_total = 0.0
            completed_cycles = 0
            # Position estimated from the commanded speeds and the real time
            # each speed was held. The reported "pos" is NOT used because in
            # speed mode it does not reliably follow direction changes (it
            # made the correction run away). The estimate is calibrated with
            # SINUSOIDAL_STEPS_PER_DEG, so it is also what the chart shows.
            x_est = 0.0
            v_last = 0.0
            t_last = 0.0
            peak_max = 0.0
            peak_min = 0.0
            self._queue_tilt_angle(0.0)

            while self._tilt_motor_running:
                if self._pause_pressed:
                    self._postep.set_requested_speed(0)
                    self._set_pause_movement_flags()
                    pause_start = time.monotonic()
                    # Account for the movement until the stop command.
                    x_est += v_last * (pause_start - t0 - paused_total - t_last)
                    v_last = 0.0
                    self._queue_tilt_angle(x_est / steps_per_deg)
                    while self._tilt_motor_paused and self._tilt_motor_running:
                        time.sleep(dt)
                    paused_total += time.monotonic() - pause_start
                    t_last = time.monotonic() - t0 - paused_total
                    self._resume_pressed = False
                    if not self._tilt_motor_running:
                        break

                # Phase time excludes paused time, so the sine continues
                # from where it was paused.
                t = time.monotonic() - t0 - paused_total
                if t >= total_duration:
                    break

                x_est += v_last * (t - t_last)
                t_last = t
                self._queue_tilt_angle(x_est / steps_per_deg)
                x_ref = reference(t)

                # Feedforward speed to the next reference point + correction
                # for the time the previous command was actually held.
                v_ref = (reference(t + dt) - x_ref) / dt
                v_cmd = v_ref + SINUSOIDAL_KP * (x_ref - x_est)
                v_cmd = max(-max_speed, min(max_speed, v_cmd))
                # Never command a step that would take the estimate past the
                # min/max tilt within the next interval.
                x_next = x_est + v_cmd * dt
                if x_next > upper_limit:
                    v_cmd = max(0.0, (upper_limit - x_est) / dt)
                elif x_next < lower_limit:
                    v_cmd = min(0.0, (lower_limit - x_est) / dt)
                speed = abs(v_cmd)
                if speed < 1:
                    # Avoid overflowing the PoStep step period register.
                    speed = 0
                    v_cmd = 0.0
                direction = "cw" if v_cmd * SINUSOIDAL_CW_SIGN >= 0 else "ccw"
                self._postep.set_requested_speed(speed, direction)
                v_last = v_cmd
                peak_max = max(peak_max, x_est)
                peak_min = min(peak_min, x_est)

                cycles_done = int(max(t - ramp, 0) * frequency)
                if cycles_done > completed_cycles:
                    completed_cycles = cycles_done
                    print(
                        f"Sinusoidal cycle {completed_cycles}: estimated peaks "
                        f"{peak_min / steps_per_deg:.2f} / "
                        f"{peak_max / steps_per_deg:.2f} deg"
                    )
                    peak_max = 0.0
                    peak_min = 0.0
                    # Same as constant movement: report the running repetition.
                    if repetitions == 0 or completed_cycles < repetitions:
                        self.send_repetitions_websocket(completed_cycles + 1)

                time.sleep(dt)

            self._postep.set_requested_speed(0)
            # Final point where the motor actually stopped.
            t = time.monotonic() - t0 - paused_total
            x_est += v_last * (t - t_last)
            self._queue_tilt_angle(x_est / steps_per_deg)
        except Exception as e:
            print(f"Error in sinusoidal tilt motor thread: {e}")
        finally:
            try:
                self._postep.set_requested_speed(0)
            except Exception as e:
                print(f"Error stopping tilt motor: {e}")
            self._tilt_motor_running = False
            if self._save_measurements_task:
                self._save_measurements_task.join(timeout=3)
                self._save_measurements_task = None
            self._send_tilt_stopped_websocket()
            self._tilt_motor_start_time = 0
            self._is_moving = False
            self._motor_status = MotorStatus.IDLE
            self._postep.run_sleep(False)

    def send_repetitions_websocket(self, repetitions: int):
        """Send measurements to the WebSocket."""
        try:
            print(f"SENDING REPETITIONS: {repetitions}")
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

        # Do not clear the entry of a run that was started in the meantime.
        if self._current_entry_id == entry_id:
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
        microstepping: int | None,
        repetitions: int | None,
        min_tilt: int | None,
        max_tilt: int | None,
        end_position: int | None = 1,
        move_duration: float = 1,
        standstill_duration_left: int = 0.2,
        standstill_duration_horizontal: int = 0.2,
        standstill_duration_right: int = 0.2,
        movement_mode: str = "constant",
        frequency: float | None = None,
    ) -> bool:
        """Tilt motor from min to max in non-stop motion."""
        if movement_mode not in {"constant", "sinusoidal"}:
            raise ValueError("Movement mode must be 'constant' or 'sinusoidal'.")
        sinusoidal = movement_mode == "sinusoidal"

        if sinusoidal:
            if frequency is None or not (
                SINUSOIDAL_MIN_FREQUENCY <= frequency <= SINUSOIDAL_MAX_FREQUENCY
            ):
                raise ValueError(
                    "Sinusoidal frequency must be between "
                    f"{SINUSOIDAL_MIN_FREQUENCY} and {SINUSOIDAL_MAX_FREQUENCY} Hz."
                )
            if None in (min_tilt, max_tilt, repetitions):
                raise ValueError(
                    "min_tilt, max_tilt and repetitions are required for "
                    "sinusoidal movement."
                )
            if (
                not (
                    -SINUSOIDAL_MAX_ANGLE_DEG
                    <= min_tilt
                    <= 0
                    <= max_tilt
                    <= SINUSOIDAL_MAX_ANGLE_DEG
                )
                or min_tilt == max_tilt
            ):
                raise ValueError(
                    "Sinusoidal movement needs min_tilt between "
                    f"-{SINUSOIDAL_MAX_ANGLE_DEG} and 0 and max_tilt between 0 "
                    f"and {SINUSOIDAL_MAX_ANGLE_DEG} deg (not both 0)."
                )
            if repetitions < 0:
                raise ValueError("repetitions must be 0 (infinite) or more.")
        else:
            if None in (
                min_tilt,
                max_tilt,
                repetitions,
                end_position,
                microstepping,
                move_duration,
            ):
                raise ValueError(
                    "min_tilt, max_tilt, repetitions, end_position, "
                    "microstepping and move_duration are required for "
                    "constant movement."
                )
            if min_tilt < self._min_position_deg or max_tilt > self._max_position_deg:
                print("Targets exceed the maximum tilt options.")
                return False

        if self._is_moving:
            print("Tilt motor is already moving.")
            return False

        # Clear control flags left over from a previous run; a stale stop flag
        # would end the new run on its first move before anything is logged.
        self._stop_pressed = False
        self._pause_pressed = False
        self._resume_pressed = False
        self._prev_pause_state = False

        entry_id = create_entry(
            name=entry_name,
            tilt_scenario_id=scenario_id,
            scenario_name=scenario_name,
        )
        self._current_entry_id = entry_id
        self._postep.run_sleep(True)
        self._postep.get_driver_settings()
        if sinusoidal:
            active_microstepping = SINUSOIDAL_MICROSTEP
            self._postep.set_driver_settings(
                step_mode=SINUSOIDAL_STEP_MODE,
                microstep=active_microstepping,
            )
        else:
            active_microstepping = microstepping
            self._postep.set_driver_settings(
                step_mode=4, microstep=active_microstepping
            )
        time.sleep(0.1)
        self._tilt_motor_running = True
        self._tilt_motor_paused = False
        self._is_moving = True
        self._motor_status = MotorStatus.MOVING
        if sinusoidal:
            self._calculated_steps = 2**SINUSOIDAL_MICROSTEP / STEPPER_STEP_ANGLE
            print(
                f"Starting sinusoidal tilt movement ({frequency} Hz, "
                f"{min_tilt} to {max_tilt} deg, repetitions {repetitions})"
            )
        else:
            # Preserve the original constant-movement conversion and behavior.
            self._calculated_steps = int(1 / (STEPPER_STEP_ANGLE / (2**microstepping)))
            min_deg = min_tilt * self._calculated_steps * GEAR_RATIO
            max_deg = max_tilt * self._calculated_steps * GEAR_RATIO
            print(f"Starting tilt motor with min_deg: {min_deg}, max_deg: {max_deg}")
        if sinusoidal:
            self._tilt_motor_task = threading.Thread(
                target=self._sinusoidal_tilt_motor_thread,
                args=(frequency, min_tilt, max_tilt, repetitions),
                daemon=True,
            )
        else:
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
            scenario_data=scenario.model_dump(),
        )

    def save_move_scenario(self, scenario: MoveScenario) -> bool:
        """Save a move scenario."""
        scenario_id = create_tilt_scenario(scenario.model_dump())
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
