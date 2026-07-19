<script setup lang="ts">
import type { QueryExecution } from "../types";

defineProps<{ execution: QueryExecution | null; loading: boolean }>();

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
    <div v-else-if="execution.result" class="table-scroll">
      <table>
        <thead>
          <tr><th>#</th><th v-for="column in execution.result.columns" :key="column">{{ column }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in execution.result.rows" :key="rowIndex">
            <td class="row-number">{{ rowIndex + 1 }}</td>
            <td v-for="(value, columnIndex) in row" :key="columnIndex" :class="{ null: value === null }">
              {{ display(value) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
