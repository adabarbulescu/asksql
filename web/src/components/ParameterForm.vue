<script setup lang="ts">
import { computed } from "vue";
import { useStudioStore } from "../stores/studio";

const studio = useStudioStore();
const saved = computed(() => studio.savedQueries.find((item) => item.id === studio.activeDocument?.saved_query_id));

function inputType(type: string): string {
  if (type === "integer" || type === "decimal") return "number";
  if (type === "date") return "date";
  if (type === "datetime") return "datetime-local";
  return "text";
}
</script>

<template>
  <section v-if="saved?.parameters.length && studio.activeDocument" class="parameter-form">
    <header><strong>Parameters</strong><small>Values belong to this tab. Sensitive values are never persisted.</small></header>
    <div class="parameter-fields">
      <label v-for="parameter in saved.parameters" :key="parameter.name">
        <span>{{ parameter.description || parameter.name }}<b v-if="parameter.required">*</b></span>
        <select v-if="parameter.data_type === 'boolean'" v-model="studio.activeDocument.parameter_values[parameter.name]">
          <option value="">Select…</option><option :value="true">True</option><option :value="false">False</option>
        </select>
        <input v-else v-model="studio.activeDocument.parameter_values[parameter.name]"
          :type="parameter.sensitive ? 'password' : inputType(parameter.data_type)"
          :step="parameter.data_type === 'decimal' ? 'any' : undefined"
          :placeholder="parameter.default_value == null ? parameter.name : String(parameter.default_value)" />
        <small>{{ parameter.data_type }}<template v-if="parameter.sensitive"> · sensitive</template></small>
      </label>
    </div>
  </section>
</template>
