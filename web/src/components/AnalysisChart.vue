<script setup lang="ts">
import { computed } from "vue";

import type { AnalysisChart } from "../types";

const props = defineProps<{ chart: AnalysisChart }>();
const values = computed(() => props.chart.series[0]?.values ?? []);
const bounds = computed(() => {
  const low = Math.min(0, ...values.value);
  const high = Math.max(0, ...values.value);
  return { low, high, range: high - low || 1 };
});
const points = computed(() => values.value.map((value, index) => {
  const x = values.value.length === 1 ? 300 : 36 + index * (528 / (values.value.length - 1));
  const y = 18 + ((bounds.value.high - value) / bounds.value.range) * 150;
  return { x, y, value, label: props.chart.labels[index] ?? "" };
}));
const line = computed(() => points.value.map((point) => `${point.x},${point.y}`).join(" "));
const zeroY = computed(() => 18 + (bounds.value.high / bounds.value.range) * 150);
</script>

<template>
  <article class="analysis-chart">
    <header><strong>{{ chart.title }}</strong><span>{{ chart.series[0]?.name }}</span></header>
    <svg viewBox="0 0 600 205" role="img" :aria-label="chart.title">
      <line x1="36" x2="564" :y1="zeroY" :y2="zeroY" class="chart-axis" />
      <template v-if="chart.type === 'line'">
        <polyline :points="line" class="chart-line" />
        <circle v-for="point in points" :key="point.label" :cx="point.x" :cy="point.y" r="4" class="chart-point">
          <title>{{ point.label }}: {{ point.value.toLocaleString() }}</title>
        </circle>
      </template>
      <template v-else>
        <rect
          v-for="(point, index) in points" :key="point.label"
          :x="44 + index * (512 / Math.max(points.length, 1))"
          :y="Math.min(point.y, zeroY)"
          :width="Math.max(8, 512 / Math.max(points.length, 1) - 10)"
          :height="Math.max(1, Math.abs(zeroY - point.y))"
          :class="['chart-bar', { negative: point.value < 0 }]"
        ><title>{{ point.label }}: {{ point.value.toLocaleString() }}</title></rect>
      </template>
      <text
        v-for="(point, index) in points" :key="`label-${point.label}`"
        :x="chart.type === 'bar' ? 44 + index * (512 / Math.max(points.length, 1)) : point.x"
        y="194" class="chart-label"
      >{{ point.label.slice(0, 12) }}</text>
    </svg>
  </article>
</template>
