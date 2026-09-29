<template>
  <div ref="chartContainer">
    <apexchart
      type="line"
      :options="chartOptions"
      :series="series"
      :height="props.chartHeight"
    />
  </div>

  <!-- Filename Modal -->
  <FilenameModal
  :visible="showFilenameModal"
  :scenarioName="props.scenario_name"
  :endTimestamp="endTimestamp"
  :prefix="filenamePrefix"
  :type="props.type"
  @update:visible="val => (showFilenameModal = val)"
  @confirm="({ prefix, filename }) => { filenamePrefix = prefix; downloadCsv(filename) }"
/>
<Toast></Toast>
</template>

<script setup lang="ts">
	import Toast from 'primevue/toast';
	import { useToast } from 'primevue/usetoast';
  import { tiltMotorApi, rotaryMotorApi, peristalticMotorApi } from "../api";
	const toast = useToast();
	const showError = (message: string) => {
	  toast.add({
	  severity: 'error', // 'success', 'info', 'warn', 'error'
	  summary: 'Error',
	  detail: message,
	  life: 3000 // milliseconds (optional)
	  });
	}

import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import FilenameModal from "./FilenameModal.vue";
//endTimestamp in ISO 8601 format
const chartContainer = ref<HTMLElement | null>(null);
const entryId = ref(0);
const handleToolbarClick = async (event: MouseEvent) => {
  const target = event.target as HTMLElement;
  if (target.closest('.apexcharts-toolbar')) {
    if (!props.isMoving) {
      const newData = await fetchMeasurements(entryId.value, props.type ?? 0);
      if (newData) {
        seriesData.value = newData;
        series.value[0].data = decimateToMax(seriesData.value, 1000);
      } else {
        seriesData.value = [];
        series.value[0].data = [];
      }
    }
  }
};

function decimateToMax(
  data: Array<{ x: number; y: number }>,
  maxPoints: number
): Array<{ x: number; y: number }> {
  if (data.length <= maxPoints) return data;
  const result: Array<{ x: number; y: number }> = [];
  const step = (data.length - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints; i++) {
    const index = i === maxPoints - 1 ? data.length - 1 : Math.round(i * step);
    result.push(data[index]);
  }
  return result;
}
// fetch measurements from the database depending on the type of entry
const fetchMeasurements = async (entryId: number, type: number) => {

  try {
    let measurements: any[] = [];
    if (props.type === 0) {
      measurements = await tiltMotorApi.getMeasurements(entryId, null, 100000);
    } else if (props.type === 1) {
      measurements = await rotaryMotorApi.getMeasurements(entryId, null, 100000);
    } else if (props.type === 2) {
      measurements = await peristalticMotorApi.getMeasurements(entryId, null, 100000);
    }
    return measurements.map((m) => ({
      x: m.time,
      y: props.type === 0 ? m.angle : props.type === 1 ? m.speed : Math.abs(m.flow ?? 0),
    }));
  } catch (err: any) {
  }
};


const endTimestamp = ref('');
const props = defineProps<{
  entryId?: number;
  scenario_name?: string;
  isMoving?: boolean;
  runId?: number;
  minVal?: number;
  maxVal?: number;
  type: number;
  chartHeight: number | 600;
}>();

// Tilt measurements arrive in batches of ~25-50 points every 0.5 s, so a
// 20-point window would only show a fraction of a second of the movement.
const maxDataPoints = props.type === 0 ? 1000 : 20;
const websocketUrl =
  (window.location.protocol === "https:" ? "wss://" : "ws://") +
  window.location.hostname +
  ":8000/ws/motor";

let socket: WebSocket | null = null;

const showFilenameModal = ref(false);
const filenamePrefix = ref('');
const seriesData = ref([] as Array<{ x: number; y: number }>);
const series = ref([
  {
    name: props.type === 0 ? "Angle" : props.type === 1 ? "RPM" : "Flow (mL/min)",
    data: [] as Array<{ x: number; y: number }>,
  },
]);

const chartOptions = ref({
  chart: {
    type: "line",
    height: props.type === 0 ? 510 : props.type === 1 ? 460 : 460,
    animations: {
      enabled: false,
      animateGradually: {
        enabled: true,
        delay: 10,
      },
    },
    toolbar: {
      show: true,
      tools: {
        download: false,
        customIcons: [
        {
          icon: '<span style="margin-left: 4px; padding: 2px 4px 2px 4px; font-size: 12px; border: 1px solid #6e8192; border-radius: 8px;">CSV</span>',
          title: 'Download CSV',
          index: 5,
          class: 'custom-csv-download',
          appendTo: 'right',
          click: () => {
            showFilenameModal.value = true;
          },
        },
      ],
      },
    },

    zoom: {
      enabled: true,
    },
  },
  dataLabels: {
    enabled: false,
  },
  stroke: {
    curve: "smooth",
    width: 2,
  },
  xaxis: {
    type: "numeric",
    title: {
      text: "Time",
    },
    labels: {
      formatter: (val: number) => {
        if (val === undefined || val === null || isNaN(val)) {
          return '0';
        }
        return val.toFixed(2);
      },
    },
  },
  yaxis: {
  title: {
    text: props.type === 0 ? "Angle" : props.type === 1 ? "RPM" : "Flow (mL/min)",
  },
  min: props.minVal !== undefined ? Number((props.minVal).toFixed(0)) + Number((props.minVal / 2).toFixed(0)) : -20,
  max: props.maxVal !== undefined ? Number((props.maxVal).toFixed(0)) + Number((props.maxVal / 2).toFixed(0)) : 20,
  labels: {
    formatter: (val: number) => {
      if (val === undefined || val === null || isNaN(val)) {
        return '0';
      }
      return val.toFixed(0);
    },
  },
},
tooltip: {
  x: {
    formatter: (val: number) => {
      if (val === undefined || val === null || isNaN(val)) {
        return '0';
      }
      return val.toFixed(2);
    },
  },
  y: {
    formatter: (val: number) => {
      if (val === undefined || val === null || isNaN(val)) {
        return '0';
      }
      return val.toFixed(0);
    },
  },
},
  legend: {
    show: true,
    position: "top",
  },
  grid: {
    borderColor: "#e7e7e7",
    row: {
      colors: ["#f3f3f3", "transparent"],
      opacity: 0.5,
    },
  },
});

const downloadCsv = (customFilename?: string) => {
  if (props.isMoving){
    showError("Motor is moving. Please stop it before downloading the CSV.");
    return;
  }
  const points = seriesData.value;
  const header = 'Timestamp (ms),' + (props.type === 0 ? "Angle (deg)" : props.type === 1 ? "RPM" : "Flow (mL/min)") + '\n';
  const rows = points
  .map((p) => {
    const yVal = props.type === 2 ? Math.abs(p.y) : p.y;
    return `${(p.x * 1000).toFixed(2)},${yVal.toFixed(2)}`;
  })
    .join('\n');

  const csv = header + rows;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = customFilename || (props.type === 0 ? "tilt.csv" : props.type === 1 ? "rotate.csv" : "peristaltic.csv");
  a.click();
  URL.revokeObjectURL(url);
};

const addPoints = (points: Array<{ x: number; y: number }>) => {
  series.value[0].data.push(...points);
  //fullSeries.value[0].data.push(...points);
    while (series.value[0].data.length > maxDataPoints) {
    series.value[0].data.shift();
  }
};


const setupWebSocket = () => {
  if (socket) {
    socket.close();
    socket = null;
  }

  socket = new WebSocket(websocketUrl);

  socket.onopen = () => {
  };

  socket.onmessage = (event) => {
  try {
    const msg = JSON.parse(event.data);
    if (!msg.data) return;
    if (Array.isArray(msg.data) && msg.data[0]?.entry_id) {
      entryId.value = msg.data[0].entry_id;
    }
    if (msg.type === "tilt") {
      const m = msg.data;
      addPoints(m.map((m: { time: number; angle: number }) => ({ x: Number(m.time), y: Number(m.angle) })));
    }
    if (msg.type === "rotate") {
      const m = msg.data;
        addPoints(m.map((m: { time: number; speed: number; direction: string }) => ({ x: Number(m.time), y: m.speed * (m.direction === 'cw' ? 1 : -1) })));
    }
    if (msg.type === "peristaltic") {
      const m = msg.data;
      addPoints(m.map((m: { time: number; flow: number; direction: string }) => ({ x: Number(m.time), y: m.flow * (m.direction === 'cw' ? 1 : -1) })));
    }
  } catch (e) {
    console.error("Error parsing WebSocket message:", e);
  }
};

  socket.onerror = (event) => {
    console.error("WebSocket error:", event);
  };

  socket.onclose = () => {
  };
};

watch(
  () => [props.isMoving, props.entryId, props.scenario_name],
  () => {
    if (!props.isMoving) {
      endTimestamp.value = new Date().toISOString();
      return;
    }
  }
);

watch(
  () => props.runId,
  () => {
    if (props.runId) {
      series.value[0].data = [];
    }
  }
);

watch(
  () => [props.minVal, props.maxVal],
  () => {
    chartOptions.value = {
      ...chartOptions.value,
      yaxis: {
        ...chartOptions.value.yaxis,
        min: (props.minVal !== undefined && !isNaN(props.minVal)
          ? Number((props.minVal * 1.5).toFixed(0))
          : -10),
        max: (props.maxVal !== undefined && !isNaN(props.maxVal)
          ? Number((props.maxVal * 1.5).toFixed(0))
          : 10),
      },
    };
  },
);
onMounted(() => {
  setupWebSocket();

  // Wait for next tick to ensure chart is rendered
  setTimeout(() => {
    if (chartContainer.value) {
      chartContainer.value.addEventListener('click', handleToolbarClick);
    }
  }, 100);
});

onBeforeUnmount(() => {
  if (socket) {
    socket.close();
    socket = null;
  }

  if (chartContainer.value) {
    chartContainer.value.removeEventListener('click', handleToolbarClick);
  }
});
</script>

<style scoped>
.custom-csv-download {
  cursor: pointer;
  color: #007bff;
  margin-bottom: 8px;
  border-radius: 8px;
  font-size: 6px;
  text-decoration: none;
}
</style>
