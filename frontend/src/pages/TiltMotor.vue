<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">
        <span class="text-muted-color">Tilt Motor Control</span>
      </h1>
    </div>

    <div class="grid grid-cols-3 control-grid">
      <!-- Run Configuration Card -->
      <Card style="align-self: start;" class=" col-span-1 overflow-hidden">
        <template #title>Run Configuration</template>
        <template #content>
          <div class="form-group flex flex-col gap-1">
            <FloatLabel class="w-full mb-1" variant="on">
              <InputText class="w-full" v-model="runConfiguration.name" />
              <label for="on_label">Name</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :min="-20.0"
                :max="20.0"
                :step="0.1"
                v-model="runConfiguration.min_tilt"
              />
              <label for="on_label">Minimum tilt (deg)</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :min="-20.0"
                :max="20.0"
                :step="0.1"
                v-model="runConfiguration.max_tilt"
              />
              <label for="on_label">Maximum tilt (deg)</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :maxFractionDigits="2"
                :min="0"
                :step="0.1"
                v-model="runConfiguration.move_duration"
              />
              <label for="on_label">Move duration (s)</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :maxFractionDigits="2"
                :min="0"
                :step="0.1"
                v-model="runConfiguration.repetitions"
              />
              <label for="on_label">Repetitions</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :maxFractionDigits="2"
                :min="0"
                :step="0.1"
                v-model="runConfiguration.standstill_duration_left"
              />
              <label for="on_label">Standstill duration left (s)</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :maxFractionDigits="2"
                :min="0"
                :step="0.1"
                v-model="runConfiguration.standstill_duration_horizontal"
              />
              <label for="on_label">Standstill duration horizontal (s)</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <InputNumber
                class="w-full"
                :maxFractionDigits="2"
                :min="0"
                :step="0.1"
                v-model="runConfiguration.standstill_duration_right"
              />
              <label for="on_label">Standstill duration right (s)</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <Select
                class="w-full"
                v-model="runConfiguration.end_position"
                :options="endPositionOptions"
                optionLabel="label"
                optionValue="value"
              />
              <label for="on_label">End Position</label>
            </FloatLabel>

            <FloatLabel class="w-full mb-1" variant="on">
              <Select
                class="w-full"
                v-model="runConfiguration.microstepping"
                :options="microstepOptions"
                optionLabel="label"
                optionValue="value"
              />
              <label for="on_label">Microstepping</label>
            </FloatLabel>
          </div>
        </template>
        <template #footer>
          <!-- make this div be 100% width of parent-->
          <div class="footer-separator"></div>
            <div class="flex justify-end ml-1">
              <div class="justify-end">
                <Button
                  v-if="runConfiguration && !isTilting && !tiltPaused"
                  class="m-2 btn"
                  severity="warn"
                  @click="moveMotorHome"
                >
                  Homing
                </Button>

                <Button
                  v-if="runConfiguration && !isTilting && !tiltPaused"
                  class="m-2 btn"
                  severity="secondary"
                  @click="handleExportScenario"
                >
                  Export
                </Button>

                <Button
                  v-if="!isTilting && !tiltPaused && scenarios.find(el => el.id === runConfiguration.scenario_id && el.name === runConfiguration.name)"
                  class="m-2 btn"
                  severity="secondary"
                  @click="handleUpdateScenario"
                >
                <span>Update Scenario</span>

                </Button>

                <Button
                  v-if="!isTilting && !tiltPaused && !scenarios.find(el => el.id === runConfiguration.scenario_id && el.name === runConfiguration.name)"
                  class="m-2 btn"
                  severity="info"
                  @click="handleSaveScenario"
                >
                  Save Scenario
                </Button>

                <Button
                  v-if="!isTilting && !tiltPaused"
                  class="m-2 btn"
                  @click="tiltMotor"
                >
                  Tilt
                </Button>

                <Button
                  v-if="tiltPaused"
                  class="m-2 btn"
                  severity="secondary"
                  @click="resumeTilt"
                >
                  Resume Tilt
                </Button>

                <div v-if="isTilting">
                  <Button v-if="!tiltPaused"
                    class="mt-2 ml-1 btn"
                    severity="info"
                    @click="pauseTilt"
                  >
                    Pause Tilt
                  </Button>
                  <Button
                    class="mt-2 ml-1 btn"
                    severity="danger"
                    @click="stopTilt"
                  >
                    Stop Motor
                  </Button>
                </div>
              </div>
            </div>
          </template>
      </Card>

      <!-- Graph Card -->
      <Card style="align-self: start;" class="col-span-2">
        <template #title>
          <span class="text-muted-color">Real-time Tilt Movements</span>
          <span class="ml-4 text-sm">Repetitions: {{ repetitionCounter }}</span>
        </template>
        <template #content>
          <MovementsChart
            :key="runId"
            :isMoving="isTilting"
            :runId="runId"
            :chartHeight="510"
            :scenario_name="runConfiguration.scenario_name"
            :maxVal="Number(runConfiguration.max_tilt) || 20"
            :minVal="Number(runConfiguration.min_tilt) || -20"
            :type=0
          />
        </template>
      </Card>

      <!-- Move Scenarios Card -->
      <Card class="col-span-3">
        <template #title>Move Scenarios</template>
        <template #content>
          <div v-if="scenariosError" class="alert alert-danger">
            {{ scenariosError }}
          </div>
          <div v-else>
            <div class="flex justify-end m-1">
              <FileUpload
                @select="handleFileSelect"
                mode="basic"
                name="importScenario"
                customUpload
                auto
                chooseLabel="Import"
              />
            </div>

            <div class="overflow-auto table-responsive">
              <DataTable :value="scenarios" tableStyle="min-width: 50rem">
                <Column field="imported" header="DB" style="width: 4%">
                  <template #body="slotProps">
                    <i class="pi pi-database" v-if="!slotProps.data.imported"></i>
                  </template>
                </Column>

                <Column field="name" header="Name" />
                <Column field="min_tilt" header="Min Tilt" />
                <Column field="max_tilt" header="Max Tilt" />
                <Column field="move_duration" header="Move Duration (s)" />
                <Column field="repetitions" header="Repetitions" />
                <Column field="standstill_duration_left" header="Standstill Duration Left (s)" />
                <Column field="standstill_duration_horizontal" header="Standstill Duration Horizontal (s)" />
                <Column field="standstill_duration_right" header="Standstill Duration Right (s)" />

                <Column field="end_position" header="End Position">
                  <template #body="slotProps">
                    {{ endPositionOptions.find(option => option.value === slotProps.data.end_position)?.label }}
                  </template>
                </Column>

                <Column field="microstepping" header="Microstepping">
                  <template #body="slotProps">
                    {{ microstepOptions.find(option => option.value === slotProps.data.microstepping)?.label }}
                  </template>
                </Column>

                <Column field="actions" style="width: 15%" header="Actions">
                  <template #body="slotProps">
                    <Button
                      icon="pi pi-pencil"
                      style="width: 60px"
                      severity="primary"
                      class="ml-1 btn"
                      @click="loadScenario(slotProps.data)"
                    >
                      Load
                    </Button>
                    <Button
                      icon="pi pi-trash"
                      style="width: 60px"
                      class="ml-2 btn"
                      severity="danger"
                      @click="deleteScenarioModalActive = true; removeId = slotProps.data.id"
                    >
                      Delete
                    </Button>
                  </template>
                </Column>
              </DataTable>
            </div>
          </div>
        </template>
      </Card>
    </div>

    <!-- Delete Scenario Dialog -->
    <div
      v-if="deleteScenarioModalActive"
      class="modal-overlay"
      @click.self="deleteScenarioModalActive = false"
    >
      <Dialog
        v-model:visible="deleteScenarioModalActive"
        modal
        header="Delete Scenario"
        :style="{ width: '25rem' }"
      >
        <div class="flex flex-column gap-3">
          <p>Are you sure you want to delete this scenario?</p>
        </div>

        <template #footer>
          <Button
            label="Cancel"
            severity="secondary"
            outlined
            @click="deleteScenarioModalActive = false"
          />
          <Button
            label="Delete"
            severity="danger"
            @click="removeScenario(removeId); deleteScenarioModalActive = false; removeId = 0"
          />
        </template>
      </Dialog>
    </div>

    <Toast></Toast>
  </div>
</template>

<script setup lang="ts">
// ============================================================
// Imports
// ============================================================
import { ref, onMounted, onBeforeUnmount } from "vue";
import { tiltMotorApi, type MotorStatus, type MoveScenario, type RunConfiguration, generalApi } from "../api";
import MovementsChart from "../components/MovementsChart.vue";
import Button from 'primevue/button';
import Card from 'primevue/card';
import InputText from 'primevue/inputtext';
import InputNumber from 'primevue/inputnumber';
import FloatLabel from 'primevue/floatlabel';
import DataTable from 'primevue/datatable';
import FileUpload from 'primevue/fileupload';
import Column from 'primevue/column';
import Select from 'primevue/select';
import Dialog from 'primevue/dialog';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';

// ============================================================
// Toast / UI helpers
// ============================================================
const toast = useToast();

const showSuccess = (message: string) => {
  toast.add({
    severity: 'success',
    summary: 'Success',
    detail: message,
    life: 3000
  });
};

const showError = (message: string) => {
  toast.add({
    severity: 'error',
    summary: 'Error',
    detail: message,
    life: 3000
  });
};

// ============================================================
// Motor state
// ============================================================
const status = ref<MotorStatus | null>(null);
const isTilting = ref(false);
const tiltPaused = ref(false);
const repetitionCounter = ref(0);
const runId = ref(0);
const statusError = ref<string | null>(null);
let statusInterval: number | null = null;

// ============================================================
// Scenario state
// ============================================================
const scenarios = ref<MoveScenario[]>([]);
const scenariosError = ref<string | null>(null);
const deleteScenarioModalActive = ref(false);
const removeId = ref(0);

// ============================================================
// Run configuration
// ============================================================
const runConfiguration = ref<RunConfiguration>({
  name: "",
  scenario_name: "",
  scenario_id: null,
  min_tilt: null,
  max_tilt: null,
  move_duration: null,
  repetitions: null,
  end_position: null,
  standstill_duration_left: null,
  standstill_duration_horizontal: null,
  standstill_duration_right: null,
  microstepping: null,
});

// ============================================================
// Select options
// ============================================================
const endPositionOptions = ref([
  { label: 'Left', value: 2 },
  { label: 'Horizontal', value: 1 },
  { label: 'Right', value: 0 },
]);

const microstepOptions = ref([
  { label: '1/4 step', value: 2 },
  { label: '1/8 step', value: 3 },
  { label: '1/16 step', value: 4 },
  { label: '1/32 step', value: 5 },
  { label: '1/64 step', value: 6 },
  { label: '1/128 step', value: 7 },
  { label: '1/256 step', value: 8 },
]);

// ============================================================
// WebSocket
// ============================================================
const socket = ref<WebSocket | null>(null);

const setupWebSocket = () => {
  if (socket.value) {
    socket.value.close();
    socket.value = null;
  }
  socket.value = new WebSocket("ws://" + window.location.hostname + ":8000/ws/motor");
  socket.value.onopen = () => {};
  socket.value.onmessage = (event: MessageEvent) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "tilt_stopped") {
      isTilting.value = false;
      tiltPaused.value = false;
    }
    if (msg.type === "repetitions") {
      repetitionCounter.value = msg.repetitions;
    }
  };
};

// ============================================================
// Motor control functions
// ============================================================
const moveMotorHome = async () => {
  try {
    await tiltMotorApi.moveMotorHome();
  } catch (err: any) {
    showError("Error with moving motor to home.");
  }
};

const tiltMotor = async () => {
  try {
    runId.value++;
    repetitionCounter.value = 1;
    const entry_name = `entry_${new Date().toISOString().replace(/[-:.]/g, "").slice(0,15)}`;
    localStorage.setItem('last_ran_scenario', JSON.stringify({
      scenario_id: runConfiguration.value.scenario_id,
      scenario_name: runConfiguration.value.scenario_name
    }));
    const response = await tiltMotorApi.tiltMotor(entry_name, {
      ...runConfiguration.value,
    });
    isTilting.value = response.success;
  } catch (err: any) {
    showError("Error with starting tilting.");
  }
};

const resumeTilt = async () => {
  try {
    await tiltMotorApi.resumeTilt();
    isTilting.value = true;
    tiltPaused.value = false;
  } catch (err: any) {
    showError("Error with resuming tilting.");
  }
};

const pauseTilt = async () => {
  try {
    await tiltMotorApi.pauseTilt();
    isTilting.value = false;
    tiltPaused.value = true;
  } catch (err: any) {
    showError("Error with pausing tilting.");
  }
};

const stopTilt = async () => {
  try {
    await tiltMotorApi.stopTilt();
    isTilting.value = false;
    tiltPaused.value = false;
  } catch (err: any) {
    showError("Error with stopping tilting.");
  }
};

// ============================================================
// Status fetching
// ============================================================
const fetchStatus = async () => {
  try {
    statusError.value = null;
    status.value = await tiltMotorApi.getStatus();
    if (status.value?.is_moving) {
      isTilting.value = true;
    }
  } catch (err: any) {
    statusError.value =
      err.response?.data?.detail || err.message || "Failed to fetch status";
    console.error("Error fetching status:", err);
  }
};

// ============================================================
// Scenario functions
// ============================================================
const fetchScenarios = async () => {
  try {
    scenariosError.value = null;
    scenarios.value = await tiltMotorApi.getMoveScenarios();
  } catch (err: any) {
    scenariosError.value =
      err.response?.data?.detail || err.message || "Failed to fetch scenarios";
    console.error("Error fetching scenarios:", err);
  }
};

const fetchScenario = async (scenarioId: number) => {
  try {
    const response = await tiltMotorApi.getMoveScenario(scenarioId);
    runConfiguration.value = {
      scenario_id: response.id || null,
      scenario_name: response.name || null,
      ...response,
    };
  } catch (err: any) {
    showError("Error with fetching scenario.");
  }
};

const loadScenario = (scenario: MoveScenario) => {
  runConfiguration.value = {
    scenario_id: scenario.id || null,
    scenario_name: scenario.name || null,
    ...scenario,
  };
};

const removeScenario = async (scenarioId: number) => {
  try {
    const response = await tiltMotorApi.removeMoveScenario(scenarioId);
    if (response.success) {
      showSuccess("Scenario deleted successfully.");
      fetchScenarios();
    }
  } catch (err: any) {
    showError("Error with deleting scenario.");
  }
};

const handleUpdateScenario = async () => {
  try {
    const response = await tiltMotorApi.updateMoveScenario({
      ...runConfiguration.value,
    });
    if (response.success) {
      fetchScenarios();
      showSuccess("Scenario updated successfully.")
    }
  } catch (err: any) {
    if (err.response.status === 422) {
      showError("Error with updating scenario. Fields missing.");
    } else {
      showError("Error with updating scenario.");
    }
  }
};

const handleSaveScenario = async () => {
  try {
    const response = await tiltMotorApi.saveMoveScenario({
      id: null,
      ...runConfiguration.value,
    });
    if (response.success) {
      await fetchScenarios();
      showSuccess("Scenario saved successfully.");
      loadScenario(scenarios.value.find(scenario => scenario.id === response.tilt_scenario_id) as MoveScenario);
    }
  } catch (err: any) {
    console.error("Error with saving scenario:", err.response.data.detail);
    if (err.response.status === 500) {
      if (err.response.data.detail.includes("duplicate key")){
        showError("Error with saving scenario. Scenario name already exists.");
      }
      else {
        showError("Error with saving scenario. Scenario name is required.");
      }
    }
    else if (err.response.status === 422) {
      if (err.response.data.detail.length > 1) {
        showError("Error with saving scenario. Fields missing.");
      } if (err.response.data.detail.length === 1){
        showError("Error with saving scenario. " + err.response.data.detail[0].loc[1] + " " + err.response.data.detail[0].msg);
      }
    }
    else {
      showError("Error with saving scenario.");
    }
  }
};

// ============================================================
// Import / Export functions
// ============================================================
const handleExportScenario = () => {
  try {
    const scenario = {
      name: runConfiguration.value.name,
      min_tilt: runConfiguration.value.min_tilt,
      max_tilt: runConfiguration.value.max_tilt,
      repetitions: runConfiguration.value.repetitions,
      move_duration: runConfiguration.value.move_duration,
      standstill_duration_left: runConfiguration.value.standstill_duration_left,
      standstill_duration_horizontal: runConfiguration.value.standstill_duration_horizontal,
      standstill_duration_right: runConfiguration.value.standstill_duration_right,
      end_position: runConfiguration.value.end_position,
      microstepping: runConfiguration.value.microstepping,
    };
    const json = JSON.stringify(scenario, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${scenario.name}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showSuccess("Scenario exported successfully.");

  } catch (err: any) {
    showError("Error with exporting scenario.");
  }
};

const handleFileSelect = (event: any) => {
  const files = event?.files || [];
  const file = files[0];

  if (!file) {
    return;
  }

  const isJsonFile = file.type === 'application/json' ||
                     file.name?.toLowerCase().endsWith('.json');

  if (!isJsonFile) {
    showError('Invalid file type. Please select a JSON file.');
    return;
  }

  const reader = new FileReader();

  reader.onload = (e: ProgressEvent<FileReader>) => {
    try {
      const content = e.target?.result as string;

      if (!content) {
        showError('File content is empty');
        return;
      }

      const data = JSON.parse(content);

      const validateRotationScenario = (obj: any): boolean => {
        if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
          showError('Invalid format: Root must be an object');
          return false;
        }

        if (!('name' in obj) || typeof obj.name !== 'string') {
          showError('Invalid format: "name" field is required and must be a string');
          return false;
        }

        if (!('min_tilt' in obj) || typeof obj.min_tilt !== 'number') {
          showError('Invalid format: "min_tilt" field is required and must be a number');
          return false;
        }

        if (!('max_tilt' in obj) || typeof obj.max_tilt !== 'number') {
          showError('Invalid format: "max_tilt" field is required and must be a number');
          return false;
        }

        if (!('repetitions' in obj) || typeof obj.repetitions !== 'number') {
          showError('Invalid format: "repetitions" field is required and must be a number');
          return false;
        }

        if (!('move_duration' in obj) || typeof obj.move_duration !== 'number') {
          showError('Invalid format: "move_duration" field is required and must be a number');
          return false;
        }

        if (!('standstill_duration_left' in obj) || typeof obj.standstill_duration_left !== 'number') {
          showError('Invalid format: "standstill_duration_left" field is required and must be a number');
          return false;
        }

        if (!('standstill_duration_horizontal' in obj) || typeof obj.standstill_duration_horizontal !== 'number') {
          showError('Invalid format: "standstill_duration_horizontal" field is required and must be a number');
          return false;
        }

        if (!('standstill_duration_right' in obj) || typeof obj.standstill_duration_right !== 'number') {
          showError('Invalid format: "standstill_duration_right" field is required and must be a number');
          return false;
        }

        if (!('end_position' in obj) || typeof obj.end_position !== 'number') {
          showError('Invalid format: "end_position" field is required and must be a number');
          return false;
        }

        if (!('microstepping' in obj) || typeof obj.microstepping !== 'number') {
          showError('Invalid format: "microstepping" field is required and must be a number');
          return false;
        }

        return true;
      };

      if (!validateRotationScenario(data)) {
        showError('JSON file does not match the required format');
        return;
      }

      scenarios.value.push({
        name: data.name,
        min_tilt: data.min_tilt,
        max_tilt: data.max_tilt,
        repetitions: data.repetitions,
        move_duration: data.move_duration,
        standstill_duration_left: data.standstill_duration_left,
        standstill_duration_horizontal: data.standstill_duration_horizontal,
        standstill_duration_right: data.standstill_duration_right,
        end_position: data.end_position,
        microstepping: data.microstepping,
        imported: true,
      });
      showSuccess("Scenario imported successfully.");

    } catch (error) {
      showError("Error with importing scenario.");
    }
  };

  try {
    reader.readAsText(file);
  } catch (error) {
    console.error('Error starting file read:', error);
  }
};

// ============================================================
// Lifecycle hooks
// ============================================================

onMounted(() => {
  const lastRanScenarioId = localStorage.getItem('last_ran_scenario_id');
  if (lastRanScenarioId) {
    //fetchScenario(JSON.parse(lastRanScenarioId));
  }
  setupWebSocket();
  fetchStatus();
  fetchScenarios();
  statusInterval = window.setInterval(() => {
    fetchStatus();
  }, 2000);
});

onBeforeUnmount(() => {
  if (statusInterval) {
    clearInterval(statusInterval);
  }
  if (socket.value) {
    socket.value.close();
    socket.value = null;
  }
});
</script>

<style scoped>

  .page-header {
    flex-shrink: 0;
  }

  .page-title {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text-primary);
  }

  .control-grid {
    display: grid;
    gap: 1rem;
  }


  .scenarios-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .quick-actions {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .quick-actions .btn {
    width: 100%;
  }

  .card-body form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .card-body form .btn {
    width: 100%;
  }

  .alert {
    position: relative;
    padding-right: 2rem;
  }

  .alert-close {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: none;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    color: inherit;
    opacity: 0.7;
  }

  .alert-close:hover {
    opacity: 1;
  }

  .table-empty {
    text-align: center;
    color: var(--text-secondary);
    padding: 2rem !important;
  }

  .modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close:hover {
    color: var(--text-primary);
  }

.footer-separator {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    box-sizing: border-box;
    width: calc(100% + 4rem); /* extend past the card's left/right padding */
    margin: 0 -1rem 0 -2rem;  /* negative margins equal to card horizontal padding */
    border-top: 1px solid var(--surface-border); /* only top border */
    height: 0;
  }
</style>
