<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import type { QueryExecution } from "../types";

const props = defineProps<{ execution: QueryExecution | null; loading: boolean }>();
const scroller = ref<HTMLElement>();
const scrollTop = ref(0);
const viewportHeight = ref(420);
const rowHeight = 33;
const overscan = 8;
let observer: ResizeObserver | undefined;

const start = computed(() => Math.max(0, Math.floor(scrollTop.value / rowHeight) - overscan));
const end = computed(() => {
  const length = props.execution?.result?.rows.length ?? 0;
  return Math.min(length, Math.ceil((scrollTop.value + viewportHeight.value) / rowHeight) + overscan);
});
const visibleRows = computed(() => props.execution?.result?.rows.slice(start.value, end.value) ?? []);
const topSpace = computed(() => start.value * rowHeight);
const bottomSpace = computed(() => {
  const length = props.execution?.result?.rows.length ?? 0;
  return Math.max(0, (length - end.value) * rowHeight);
});
const columnCount = computed(() => (props.execution?.result?.columns.length ?? 0) + 1);

onMounted(() => {
  if (!scroller.value) return;
  observer = new ResizeObserver(([entry]) => { viewportHeight.value = entry.contentRect.height; });
  observer.observe(scroller.value);
});
onBeforeUnmount(() => observer?.disconnect());

function display(value: unknown): string {
  if (value === null) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
</script>

<template>
  <div class="result-body">
    <div v-if="loading" class="result-loading"><span class="spinner" /> Executing query…</div>
    <div v-else-if="!execution" class="result-empty">
      <div class="result-mark">⌁</div>
      <strong>Results appear here</strong>
      <span>Review the generated SQL, then run the query.</span>
    </div>
    <div v-else-if="execution.mutation" class="result-empty mutation-result">
      <div class="result-mark">✓</div>
      <strong>Write committed</strong>
      <span>{{ execution.mutation.affectedRows }} row(s) affected<template v-if="execution.mutation.lastInsertId !== null"> · inserted id {{ execution.mutation.lastInsertId }}</template></span>
    </div>
    <div v-else-if="execution.result" ref="scroller" class="table-scroll" @scroll="scrollTop = ($event.target as HTMLElement).scrollTop">
      <table>
        <thead>
          <tr><th>#</th><th v-for="column in execution.result.columns" :key="column">{{ column }}</th></tr>
        </thead>
        <tbody>
          <tr v-if="topSpace" class="virtual-spacer"><td :colspan="columnCount" :style="{ height: `${topSpace}px` }" /></tr>
          <tr v-for="(row, rowIndex) in visibleRows" :key="start + rowIndex">
            <td class="row-number">{{ start + rowIndex + 1 }}</td>
            <td v-for="(value, columnIndex) in row" :key="columnIndex" :class="{ null: value === null }">
              {{ display(value) }}
            </td>
          </tr>
          <tr v-if="bottomSpace" class="virtual-spacer"><td :colspan="columnCount" :style="{ height: `${bottomSpace}px` }" /></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
