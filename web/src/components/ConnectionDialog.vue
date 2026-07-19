<script setup lang="ts">
import { computed, ref } from "vue";

import { useStudioStore } from "../stores/studio";
import type { ConnectionProfile, ConnectionTest } from "../types";

const props = defineProps<{ profile?: ConnectionProfile }>();
const emit = defineEmits<{ close: []; saved: [] }>();
const studio = useStudioStore();
const name = ref(props.profile?.name ?? "");
const url = ref(props.profile?.url ?? "");
const testing = ref(false);
const testResult = ref<ConnectionTest | null>(null);
const localError = ref("");
const canSave = computed(() => name.value.trim() && url.value.trim() && !testing.value && !studio.busy);

async function test() {
  testing.value = true;
  localError.value = "";
  testResult.value = null;
  try {
    testResult.value = await studio.testDatabase(url.value.trim());
    url.value = testResult.value.url;
  } catch (error) {
    localError.value = error instanceof Error ? error.message : "Could not open database";
  } finally {
    testing.value = false;
  }
}

async function save() {
  localError.value = "";
  try {
    await studio.saveConnection(name.value.trim(), url.value.trim(), props.profile?.name);
    emit("saved");
  } catch (error) {
    localError.value = error instanceof Error ? error.message : "Could not save connection";
  }
}
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog connection-dialog" role="dialog" aria-modal="true" aria-labelledby="connection-title">
      <div class="dialog-heading">
        <div><span class="dialog-icon">◉</span><div><h2 id="connection-title">{{ profile ? "Edit connection" : "Add a database" }}</h2><p>Register an existing SQLite file on this machine.</p></div></div>
        <button aria-label="Close" @click="$emit('close')">×</button>
      </div>

      <form @submit.prevent="save">
        <label>
          <span>Connection name</span>
          <input v-model="name" maxlength="100" autocomplete="off" placeholder="analytics" autofocus />
          <small>Letters, numbers, dots, underscores, and hyphens.</small>
        </label>
        <label>
          <span>SQLite path or URL</span>
          <input v-model="url" maxlength="4096" autocomplete="off" placeholder="/home/ada/data/app.db" @input="testResult = null" />
          <small>The file must already exist. AskSQL never uploads or creates it.</small>
        </label>

        <div v-if="testResult" class="validation success">
          <span>✓</span><div><strong>Database opened successfully</strong><small>{{ testResult.tables }} tables · read-only validation</small></div>
        </div>
        <div v-if="localError" class="validation failure"><span>!</span><div>{{ localError }}</div></div>

        <div class="dialog-actions">
          <button type="button" class="secondary-button" :disabled="!url.trim() || testing" @click="test">
            <span v-if="testing" class="spinner" /> Test connection
          </button>
          <div>
            <button type="button" class="ghost-button" @click="$emit('close')">Cancel</button>
            <button type="submit" class="primary-button" :disabled="!canSave">
              <span v-if="studio.activity === 'save-connection'" class="spinner" />
              {{ profile ? "Save changes" : "Add connection" }}
            </button>
          </div>
        </div>
      </form>
    </section>
  </div>
</template>
