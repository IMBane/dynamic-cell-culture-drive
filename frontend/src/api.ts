import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 errors (unauthorized)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export interface MoveToDegRequest {
  degrees: number
}

export interface RotationScenario {
  id: number | null
  name: string
  movements: Movement[]
}

export interface PeristalticScenario {
  id: number | null
  name: string | null
  movements: PeristalticMovement[]
  calibration: PeristalticCalibration
}

export interface RPMCalibrationRequest {
  duration: number
  rpm: number
  direction: string
}

export interface PeristalticCalibration {
  id: number
  duration: number
  low_rpm: number
  high_rpm: number
  low_rpm_volume: number
  high_rpm_volume: number
  slope: number
  name: string
  diameter: number
}

export interface PeristalticSlopeCompute {
  duration: number
  low_rpm: number
  high_rpm: number
  low_rpm_volume: number
  high_rpm_volume: number
}

export interface TubeConfiguration {
  id: number
  name: string
  diameter: number
  flow_rate: number
  preset: boolean
}
export interface PeristalticMotorCalibrationRequest {
  duration: number
  low_rpm: number
  high_rpm: number
  low_rpm_volume: number
  high_rpm_volume: number
  name: string
  diameter: number
}
export interface Movement {
  duration: number | null
  direction: string | null
  rpm: number | null
}

export interface PeristalticMovement {
  duration: number | null
  flow: number | null
  direction: string | null
}

export interface PeristalticRotateRequest {
  entry_name: string
  scenario_id: number | null
  scenario_name: string | null
  calibration_name: string
  calibration_preset: boolean
  movements: PeristalticMovement[]
}

export type MovementMode = 'constant' | 'sinusoidal'

export interface MoveScenario {
  id: number | null
  name: string | null
  movement_mode?: MovementMode
  frequency?: number | null
  min_tilt: number | null
  max_tilt: number | null
  repetitions: number | null
  move_duration: number | null
  standstill_duration_left: number | null
  standstill_duration_horizontal: number | null
  standstill_duration_right: number | null
  end_position: number | null
  microstepping: number | null
}

export interface RunConfiguration {
  name: string | null
  scenario_name: string | null
  scenario_id: number | null
  movement_mode?: MovementMode
  frequency?: number | null
  min_tilt: number | null
  max_tilt: number | null
  move_duration: number | null
  repetitions: number | null
  end_position: number | null
  microstepping: number | null
  standstill_duration_left: number | null
  standstill_duration_horizontal: number | null
  standstill_duration_right: number | null
}

export interface RotationConfiguration {
  name: string
  scenario_id: number | null
  movements: Movement[]
}

export interface PeristalticConfiguration {
  name: string
  scenario_id: number | null
  movements: PeristalticMovement[]
  calibration: Object
}

export interface MotorStatus {
  status: 'idle' | 'moving' | 'error'
  position: number
  is_moving: boolean
  initialized: boolean
}

export interface ApiResponse {
  success: boolean
  message: string
}

export interface EntryResponse {
  id: number
  scenario_id: number
  scenario_name: string
  name: string
  measurement_timestamp: string
  type: number
}

export interface TiltMeasurement {
  id: number
  entry_id: number
  tilt_scenario_id: number
  angle: number
  state: string
  time: string
}

export const tiltMotorApi = {

  // Tilt motor
  async tiltMotor(entry_name: string, runConfiguration: RunConfiguration): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/tilt/tilt', { entry_name, ...runConfiguration })
    return response.data
  },

  // Stop tilting motor
  async stopTilt(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/tilt/stop-tilt')
    return response.data
  },

  // Resume tilting motor
  async resumeTilt(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/tilt/resume-tilt')
    return response.data
  },

  // Pause tilting motor
  async pauseTilt(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/tilt/pause-tilt')
    return response.data
  },

  // Get motor status
  async getStatus(): Promise<MotorStatus> {
    const response = await api.get<MotorStatus>('/tilt/status')
    return response.data
  },

  // Get move scenarios
  async getMoveScenarios(): Promise<MoveScenario[]> {
    const response = await api.get<MoveScenario[]>('/tilt/move-scenarios')
    return response.data
  },

  // Get move scenario
  async getMoveScenario(scenarioId: number): Promise<MoveScenario> {
    const response = await api.get<MoveScenario>(`/tilt/move-scenario/${scenarioId}`)
    return response.data
  },

  // Update move scenario
  async updateMoveScenario(scenario: MoveScenario): Promise<ApiResponse> {
    const response = await api.put<ApiResponse>(`/tilt/move-scenario/${scenario.id}`, scenario)
    return response.data
  },

  // Save move scenario
  async saveMoveScenario(scenario: MoveScenario): Promise<{ success: boolean, message: string, tilt_scenario_id: number }> {
    const response = await api.post<{ success: boolean, message: string, tilt_scenario_id: number }>('/tilt/move-scenario', scenario)
    return response.data
  },

  // Remove move scenario
  async removeMoveScenario(scenarioId: number): Promise<ApiResponse> {
    const response = await api.delete<ApiResponse>(`/tilt/move-scenario/${scenarioId}`)
    return response.data
  },

  // Get tilt measurements (entryId is required)
  async getMeasurements(entryId: string, scenarioId?: string, limit: number = 1000): Promise<TiltMeasurement[]> {
    const params = new URLSearchParams()
    params.append('entry_id', entryId)
    if (scenarioId) params.append('tilt_scenario_id', scenarioId)
    params.append('limit', limit.toString())
    const response = await api.get<TiltMeasurement[]>(`/tilt/measurements?${params.toString()}`)
    return response.data
  },

  // Get entries
  async getEntries(): Promise<EntryResponse[]> {
    const response = await api.get<EntryResponse[]>('/tilt/entries')
    return response.data
  },

  // Move motor to home
  async moveMotorHome(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/tilt/move-home')
    return response.data
  },
}

export const rotaryMotorApi = {

  // Create entry
  async rotateMotor(entry_name: string, configuration: RotationConfiguration): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/rotate/rotate', { entry_name, ...configuration })
    return response.data
  },

  // Stop rotating motor
  async stopRotate(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/rotate/stop-rotate')
    return response.data
  },

  // Resume rotating motor
  async resumeRotate(movement: number): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/rotate/resume-rotate', { params: { movement } })
    return response.data
  },

  // Pause rotating motor
  async pauseRotate(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/rotate/pause-rotate')
    return response.data
  },

  // Get motor status
  async getStatus(): Promise<MotorStatus> {
    const response = await api.get<MotorStatus>('/rotate/status')
    return response.data
  },

  // Get rotation scenarios
  async getRotationScenarios(): Promise<RotationScenario[]> {
    const response = await api.get<RotationScenario[]>('/rotate/rotation-scenarios')
    return response.data
  },

  // Save rotation scenario
  async saveRotationScenario(
    scenario: RotationScenario
  ): Promise<{ success: boolean; message: string; rotation_scenario_id: number }> {
    const response = await api.post('/rotate/rotation-scenario', scenario)
    return response.data
  },
  // Update rotation scenario
  async updateRotationScenario(scenarioId: number, scenario: RotationScenario): Promise<ApiResponse> {
    const response = await api.put<ApiResponse>(`/rotate/rotation-scenario/${scenarioId}`, scenario)
    return response.data
  },
  // Remove rotation scenario
  async removeRotationScenario(scenarioId: string): Promise<ApiResponse> {
    const response = await api.delete<ApiResponse>(`/rotate/rotation-scenario/${scenarioId}`)
    return response.data
  },

  async getMeasurements(entryId: string, rotary_scenario_id?: string, limit: number = 1000): Promise<any[]> {
    const params = new URLSearchParams()
    params.append('entry_id', entryId.toString())
    if (rotary_scenario_id) params.append('rotary_scenario_id', rotary_scenario_id.toString())
    params.append('limit', limit.toString())
    const response = await api.get<any[]>(`/rotate/measurements?${params.toString()}`)
    return response.data
  },
  // Get entries
  async getEntries(): Promise<EntryResponse[]> {
    const response = await api.get<EntryResponse[]>('/rotate/entries')
    return response.data
  },
}

export const peristalticMotorApi = {
  async getTubeConfigurations(): Promise<TubeConfiguration[]> {
    const response = await api.get<TubeConfiguration[]>('/peristaltic/tube-configurations')
    return response.data
  },
  async updateTubeConfiguration(tubeConfiguration: TubeConfiguration): Promise<ApiResponse> {
    const response = await api.put<ApiResponse>('/peristaltic/tube-configuration', tubeConfiguration)
    return response.data
  },
  async saveTubeConfiguration(tubeConfiguration: TubeConfiguration): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/peristaltic/tube-configuration', tubeConfiguration)
    return response.data
  },
  async updatePeristalticCalibration(calibration: PeristalticCalibration): Promise<ApiResponse> {
    const response = await api.put<ApiResponse>('/peristaltic/calibration', calibration)
    return response.data
  },
  async getPeristalticCalibrations(): Promise<PeristalticCalibration[]> {
    const response = await api.get<PeristalticCalibration[]>('/peristaltic/calibrations')
    return response.data
  },
  async computeSlope(slope: PeristalticSlopeCompute): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/peristaltic/calibration/compute-slope', slope)
    return response.data
  },
  async savePeristalticCalibration(calibration: PeristalticMotorCalibrationRequest): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/peristaltic/calibrate', calibration)
    return response.data
  },
  async startRPMCalibration(calibration: RPMCalibrationRequest): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/peristaltic/calibrate-rotate', calibration)
    return response.data
  },
  async stopRPMCalibration(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/peristaltic/stop-calibrate')
    return response.data
  },
  async rotateMotor(configuration: PeristalticRotateRequest): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/peristaltic/rotate', configuration)
    return response.data
  },
  async stopRotate(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/peristaltic/stop-rotate')
    return response.data
  },
  async resumeRotate(movement: number): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/peristaltic/resume-rotate', { params: { movement } })
    return response.data
  },
  async pauseRotate(): Promise<ApiResponse> {
    const response = await api.get<ApiResponse>('/peristaltic/pause-rotate')
    return response.data
  },
  async getStatus(): Promise<MotorStatus> {
    const response = await api.get<MotorStatus>('/peristaltic/status')
    return response.data
  },
  async getPeristalticScenarios(): Promise<PeristalticScenario[]> {
    const response = await api.get<PeristalticScenario[]>('/peristaltic/peristaltic-scenarios')
    return response.data
  },
  async savePeristalticScenario(scenario: PeristalticScenario): Promise<ApiResponse> {
    const response = await api.post<ApiResponse>('/peristaltic/peristaltic-scenario', scenario)
    return response.data
  },
  async updatePeristalticScenario(scenarioId: number, scenario: PeristalticScenario): Promise<ApiResponse> {
    const response = await api.put<ApiResponse>(`/peristaltic/peristaltic-scenario/${scenarioId}`, scenario)
    return response.data
  },
  async removePeristalticScenario(scenarioId: string): Promise<ApiResponse> {
    const response = await api.delete<ApiResponse>(`/peristaltic/peristaltic-scenario/${scenarioId}`)
    return response.data
  },
  async getMeasurements(entryId: string, peristaltic_scenario_id?: string, limit: number = 1000): Promise<any[]> {
    const params = new URLSearchParams()
    params.append('entry_id', entryId.toString())
    if (peristaltic_scenario_id) params.append('peristaltic_scenario_id', peristaltic_scenario_id.toString())
    params.append('limit', limit.toString())
    const response = await api.get<any[]>(`/peristaltic/measurements?${params.toString()}`)
    return response.data
  },
  async getEntries(): Promise<EntryResponse[]> {
    const response = await api.get<EntryResponse[]>('/peristaltic/entries')
    return response.data
  },
}

export const generalApi = {
  async getGeneralStatus(): Promise<{
    tilt: {
      status: string;
      is_moving: boolean;
      movement_type: string | null;
      position: number;
      initialized: boolean;
    };
    rotary: {
      status: string;
      is_moving: boolean;
      movement_type: string | null;
      position: number;
      initialized: boolean;
    };
    peristaltic: {
      status: string;
      is_moving: boolean;
      movement_type: string | null;
      position: number;
      initialized: boolean;
    };
  }> {
    const response = await api.get('/api/status');
    return response.data;
  },
};

export const authApi = {
  // Login
  async login(username: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)
    const response = await api.post<{ access_token: string; token_type: string }>('/login', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token)
    }
    return response.data
  },

  // Logout
  logout(): void {
    localStorage.removeItem('access_token')
  },

  // Check if user is authenticated
  isAuthenticated(): boolean {
    return !!localStorage.getItem('access_token')
  },
}

export default api
