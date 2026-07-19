<script setup lang="ts">
import type { TableSchema } from "../types";

defineProps<{ tables: TableSchema[]; loading: boolean }>();
defineEmits<{ preview: [table: TableSchema] }>();
</script>

<template>
  <div class="schema-tree">
    <div v-if="loading" class="skeleton-stack">
      <span v-for="index in 5" :key="index" class="skeleton" />
    </div>
    <details v-for="table in tables" v-else :key="table.name" class="table-node">
      <summary>
        <span class="table-icon">▦</span>
        <span>{{ table.name }}</span>
        <button title="Preview table" @click.prevent="$emit('preview', table)">↗</button>
      </summary>
      <div v-for="column in table.columns" :key="column.name" class="column-node">
        <span :class="['key-dot', { primary: column.primaryKey }]">{{ column.primaryKey ? "◆" : "·" }}</span>
        <span class="column-name">{{ column.name }}</span>
        <span class="column-type">{{ column.type || "any" }}</span>
      </div>
    </details>
    <div v-if="!loading && !tables.length" class="empty-small">No tables found</div>
  </div>
</template>
