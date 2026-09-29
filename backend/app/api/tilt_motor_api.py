from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.handlers.tilt_motor import tilt_motor_handler
from app.auth import get_current_active_user
from app.models import (
    EntryResponse,
    MoveScenario,
    TiltMeasurementResponse,
    TiltMotorRequest,
    User,
)

router = APIRouter(prefix="/tilt", tags=["tilt"])


# ============================================================
# Motor control (tilt + home + status)
# ============================================================


@router.post("/tilt")
def tilt_motor(
    request: TiltMotorRequest, current_user: User = Depends(get_current_active_user)
):
    """Tilt motor from min to max in non-stop motion."""
    try:
        success = tilt_motor_handler.tilt_motor(
            entry_name=request.entry_name,
            scenario_id=request.scenario_id,
            scenario_name=request.scenario_name,
            move_duration=request.move_duration,
            repetitions=request.repetitions,
            min_tilt=request.min_tilt,
            max_tilt=request.max_tilt,
            end_position=request.end_position,
            microstepping=request.microstepping,
            standstill_duration_left=request.standstill_duration_left,
            standstill_duration_horizontal=request.standstill_duration_horizontal,
            standstill_duration_right=request.standstill_duration_right,
            movement_mode=request.movement_mode,
            frequency=request.frequency,
        )
        return {"success": success, "message": "Tilt motor started."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        print(f"Error tilting motor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stop-tilt")
def stop_tilt(current_user: User = Depends(get_current_active_user)):
    """Stop tilt motor."""
    try:
        success = tilt_motor_handler.stop_tilt_motor()
        return {"success": success, "message": "Tilt motor stopped."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pause-tilt")
def pause_tilt(current_user: User = Depends(get_current_active_user)):
    """Pause tilt motor."""
    try:
        success = tilt_motor_handler.pause_tilt_motor()
        return {"success": success, "message": "Tilt motor paused."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resume-tilt")
def resume_tilt(current_user: User = Depends(get_current_active_user)):
    """Resume tilt motor."""
    try:
        success = tilt_motor_handler.resume_tilt_motor()
        return {"success": success, "message": "Tilt motor resumed."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/move-home")
def move_home(current_user: User = Depends(get_current_active_user)):
    """Move motor to home."""
    try:
        success = tilt_motor_handler.move_to_home()
        return {"success": success, "message": "Motor moved to home."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_status(current_user: User = Depends(get_current_active_user)):
    """Get current motor status."""
    try:
        status = tilt_motor_handler.get_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Move scenarios
# ============================================================


@router.get("/move-scenarios")
def get_move_scenarios(current_user: User = Depends(get_current_active_user)):
    """Get list of move scenarios."""
    try:
        scenarios = tilt_motor_handler.get_move_scenarios()
        return scenarios
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/move-scenario/{scenario_id}", response_model=MoveScenario)
def get_move_scenario(
    scenario_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """Get a move scenario by ID."""
    try:
        scenario = tilt_motor_handler.get_move_scenario(scenario_id)
        return scenario
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Move scenarios api calls


@router.post("/move-scenario")
def save_move_scenario(
    scenario: MoveScenario,
    current_user: User = Depends(get_current_active_user),
):
    """Save a move scenario."""
    try:
        if scenario.name == "":
            raise HTTPException(status_code=400, detail="Scenario name is required")
        scenario_id = tilt_motor_handler.save_move_scenario(scenario)
        return {
            "success": True,
            "message": "Move scenario saved.",
            "tilt_scenario_id": scenario_id,
        }
    except Exception as e:
        print(f"Error saving move scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/move-scenario/{scenario_id}")
def update_move_scenario(
    scenario_id: int,
    scenario: MoveScenario,
    current_user: User = Depends(get_current_active_user),
):
    """Update a move scenario."""
    try:
        success = tilt_motor_handler.update_move_scenario(scenario_id, scenario)
        return {
            "success": success,
            "message": "Move scenario updated.",
        }
    except Exception as e:
        print(f"Error updating move scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/move-scenario/{scenario_id}")
def remove_move_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """Remove a move scenario."""
    try:
        success = tilt_motor_handler.remove_move_scenario(scenario_id)
        return {"success": success, "message": "Move scenario removed."}
    except Exception as e:
        print(f"Error removing move scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Entries
# ============================================================


@router.get("/entries", response_model=list[EntryResponse])
def get_tilt_entries(
    current_user: User = Depends(get_current_active_user),
):
    """Get all measurement entries."""
    try:
        entries = tilt_motor_handler.get_entries()
        return [
            EntryResponse(
                id=str(entry["id"]),
                scenario_id=entry["tilt_scenario_id"]
                if entry["tilt_scenario_id"]
                else None,
                scenario_name=entry["scenario_name"]
                if entry["scenario_name"]
                else None,
                name=entry["name"],
                measurement_timestamp=entry["measurement_timestamp"].isoformat(),
                type=0,
            )
            for entry in entries
        ]
    except Exception as e:
        print(f"Error getting entries: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Measurements
# ============================================================


@router.get("/measurements", response_model=list[TiltMeasurementResponse])
def get_measurements(
    entry_id: str = Query(..., description="Filter by entry ID (required)"),
    limit: int = Query(1000, description="Maximum number of results"),
    current_user: User = Depends(get_current_active_user),
):
    """Get tilt measurements for a specific entry."""
    try:
        measurements = tilt_motor_handler.get_measurements(
            entry_id=entry_id, limit=limit
        )
        return [
            TiltMeasurementResponse(
                id=str(m["id"]),
                entry_id=(m["entry_id"]),
                angle=m["angle"],
                state=m["state"],
                time=m["time"],
            )
            for m in measurements
        ]
    except Exception as e:
        print(f"Error retrieving measurements: {e}")
        raise HTTPException(status_code=500, detail=str(e))
