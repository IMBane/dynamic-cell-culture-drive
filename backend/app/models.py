from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

# =========================
# Common / Shared Models
# =========================


class MotorStatus(str, Enum):
    """Status of the motor."""

    IDLE = "idle"
    MOVING = "moving"
    ERROR = "error"


class User(BaseModel):
    """User model."""

    username: str
    disabled: bool


class Configuration(BaseModel):
    """Configuration model."""

    fullscale_current: float
    idle_current: float
    isgain: int
    microstepping: int
    overheat_current: float
    torque: float


# =========================
# Tilt Motor
# =========================


class TiltMotorRequest(BaseModel):
    """Request model for tilt motor."""

    entry_name: str
    scenario_name: str | None
    scenario_id: int | None
    # Required fields depend on movement_mode, so they may be empty.
    min_tilt: Optional[int] = None
    max_tilt: Optional[int] = None
    move_duration: Optional[float] = None
    repetitions: Optional[int] = None
    end_position: Optional[int] = None
    microstepping: Optional[int] = None
    standstill_duration_left: Optional[float]
    standstill_duration_horizontal: Optional[float]
    standstill_duration_right: Optional[float]
    movement_mode: Literal["constant", "sinusoidal"] = "constant"
    frequency: Optional[float] = None  # Hz, used by "sinusoidal"


CONSTANT_SCENARIO_FIELDS = (
    "microstepping",
    "min_tilt",
    "max_tilt",
    "repetitions",
    "move_duration",
    "end_position",
    "standstill_duration_left",
    "standstill_duration_horizontal",
    "standstill_duration_right",
)

SINUSOIDAL_SCENARIO_FIELDS = ("frequency", "min_tilt", "max_tilt", "repetitions")


class MoveScenario(BaseModel):
    """Move scenario model (tilt).

    Constant scenarios use all movement fields except frequency.
    Sinusoidal scenarios use frequency, min_tilt, max_tilt and repetitions;
    the other fields are stored empty.
    """

    id: Optional[int] = None
    name: str
    movement_mode: Literal["constant", "sinusoidal"] = "constant"
    frequency: Optional[float] = None
    microstepping: Optional[int] = None
    min_tilt: Optional[int] = None
    max_tilt: Optional[int] = None
    repetitions: Optional[int] = None
    move_duration: Optional[float] = None
    end_position: Optional[int] = None
    standstill_duration_left: Optional[float] = None
    standstill_duration_horizontal: Optional[float] = None
    standstill_duration_right: Optional[float] = None

    @model_validator(mode="after")
    def check_mode_fields(self) -> "MoveScenario":
        """Require the fields of the selected mode and clear the others."""
        if self.movement_mode == "sinusoidal":
            required = SINUSOIDAL_SCENARIO_FIELDS
            unused = set(CONSTANT_SCENARIO_FIELDS) - set(required)
        else:
            required, unused = CONSTANT_SCENARIO_FIELDS, {"frequency"}
        missing = [f for f in required if getattr(self, f) is None]
        if missing:
            raise ValueError(
                f"{', '.join(missing)} required for {self.movement_mode} movement"
            )
        for field in unused:
            setattr(self, field, None)
        if self.frequency is not None and self.frequency <= 0:
            raise ValueError("frequency must be greater than 0")
        return self


class EntryCreate(BaseModel):
    """Entry creation model for tilt."""

    name: str
    tilt_scenario_id: int
    scenario_name: str


class EntryResponse(BaseModel):
    """Tilt entry response model."""

    id: int
    scenario_id: Optional[int]
    scenario_name: Optional[str]
    name: str
    measurement_timestamp: str
    type: int


class TiltMeasurementCreate(BaseModel):
    """Tilt measurement creation model."""

    entry_id: int
    tilt_scenario_id: int
    angle: float
    state: MotorStatus


class TiltMeasurementResponse(BaseModel):
    """Tilt measurement response model."""

    id: int
    entry_id: int
    angle: float
    state: str
    time: float


# =========================
# Rotary Motor
# =========================


class Movement(BaseModel):
    """Movement model for rotary motor."""

    duration: int
    direction: str
    rpm: float


class RotateMotorRequest(BaseModel):
    """Request model for rotate motor."""

    entry_name: str
    scenario_id: int | None = None
    scenario_name: str | None = None
    movements: list[Movement]


class RotationScenario(BaseModel):
    """Rotation scenario model."""

    id: Optional[int]
    name: str
    movements: list[Movement]


class RotaryEntryResponse(BaseModel):
    """Rotary entry response model."""

    id: int
    rotary_scenario_id: Optional[int]
    scenario_name: Optional[str]
    name: str
    measurement_timestamp: str


class RotaryMeasurementCreate(BaseModel):
    """Rotary measurement creation model."""

    entry_id: int
    rotary_scenario_id: int
    speed: float
    direction: str


class RotaryMeasurementResponse(BaseModel):
    """Rotary measurement response model."""

    id: int
    entry_id: int
    speed: float
    direction: str
    time: float


# =========================
# Peristaltic Motor
# =========================


class PeristalticMovement(BaseModel):
    """Peristaltic movement model for peristaltic motor."""

    duration: int
    flow: float
    direction: str


class PeristalticRotateRequest(BaseModel):
    """Request model for peristaltic motor movement."""

    entry_name: str
    scenario_id: int | None = None
    scenario_name: str | None = None
    calibration_name: str
    calibration_preset: bool
    movements: list[PeristalticMovement]


class PeristalticEntryResponse(BaseModel):
    """Peristaltic entry response model."""

    id: int
    peristaltic_scenario_id: Optional[int]
    name: str
    scenario_name: Optional[str]
    measurement_timestamp: str


class PeristalticMeasurement(BaseModel):
    """Peristaltic measurement model."""

    id: int
    entry_id: int
    flow: float
    direction: str
    time: float


class TubeConfiguration(BaseModel):
    """Tube configuration model."""

    id: Optional[int]
    name: str
    diameter: float
    flow_rate: float
    preset: bool


class PeristalticCalibration(BaseModel):
    """Peristaltic calibration model (stored in DB)."""

    id: Optional[int]
    duration: int
    low_rpm: float
    high_rpm: float
    low_rpm_volume: float
    high_rpm_volume: float
    slope: float
    name: str
    diameter: float


class PeristalticSlopeCompute(BaseModel):
    """Peristaltic slope compute model."""

    duration: int
    low_rpm: float
    high_rpm: float
    low_rpm_volume: float
    high_rpm_volume: float


class PeristalticScenario(BaseModel):
    """Peristaltic scenario model."""

    id: Optional[int]
    name: str
    movements: list[PeristalticMovement]
    calibration: PeristalticCalibration | TubeConfiguration


class PeristalticMotorCalibrationRequest(BaseModel):
    """Request model for peristaltic motor calibration."""

    duration: int
    low_rpm: float
    high_rpm: float
    low_rpm_volume: float
    high_rpm_volume: float
    name: str
    diameter: float


class RPMCalibrationRequest(BaseModel):
    """Request model for generic RPM calibration."""

    duration: int
    rpm: float
    direction: str


class PeristalticMeasurementResponse(BaseModel):
    """Peristaltic measurement response model."""

    id: int
    entry_id: int
    flow: float
    direction: str
    time: float
