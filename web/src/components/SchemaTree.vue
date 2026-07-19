<script setup lang="ts">
import { computed, ref } from "vue";

import type { TableSchema } from "../types";

const props = defineProps<{ tables: TableSchema[]; loading: boolean; selected: string[] }>();
defineEmits<{ preview: [table: TableSchema]; toggle: [name: string] }>();
const search = ref("");
const filtered = computed(() => {
  const needle = search.value.trim().toLowerCase();
  if (!needle) return props.tables;
  return props.tables.filter((table) =>
    table.name.toLowerCase().includes(needle) || table.columns.some((column) => column.name.toLowerCase().includes(needle)),
  );
});
</script>

<template>
  <div class="schema-tree">
    <div class="schema-search"><input v-model="search" aria-label="Search schema" placeholder="Search tables or columns" /></div>
    <div v-if="loading" class="skeleton-stack">
      <span v-for="index in 5" :key="index" class="skeleton" />
    </div>
    <details v-for="table in filtered" v-else :key="table.name" class="table-node">
      <summary>
        <input type="checkbox" :checked="selected.includes(table.name)" title="Include in AI context" @click.stop @change="$emit('toggle', table.name)" />
        <span class="table-icon">▦</span>
        <span>{{ table.name }}</span>
        <small>{{ table.rowCount ?? '?' }} rows</small>
        <button title="Preview table" @click.prevent="$emit('preview', table)">↗</button>
      </summary>
      <div v-for="column in table.columns" :key="column.name" class="column-node">
        <span :class="['key-dot', { primary: column.primaryKey }]">{{ column.primaryKey ? "◆" : "·" }}</span>
        <span class="column-name">{{ column.name }}</span>
        <span class="column-type">{{ column.type || "any" }}</span>
      </div>
      <div v-for="key in table.foreignKeys" :key="`${key.column}-${key.referencedTable}`" class="schema-meta">↳ {{ key.column }} → {{ key.referencedTable }}.{{ key.referencedColumn }}</div>
      <div v-for="index in table.indexes" :key="index.name" class="schema-meta">⌁ {{ index.unique ? 'unique ' : '' }}{{ index.name }} ({{ index.columns.join(', ') }})</div>
    </details>
    <div v-if="!loading && !filtered.length" class="empty-small">No schema matches</div>
  </div>
</template>
