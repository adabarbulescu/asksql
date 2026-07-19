<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { saveOpenAIKey } from "../api";
import { useStudioStore } from "../stores/studio";

const emit = defineEmits<{ close: [] }>();
const studio = useStudioStore();
const [initialProvider, initialName] = studio.model.includes(":")
  ? studio.model.split(/:(.*)/s, 2)
  : ["ollama", studio.model];
const provider = ref(initialProvider === "openai" ? "openai" : "ollama");
const name = ref(initialName || "qwen2.5-coder:7b");
const candidate = computed(() => `${provider.value}:${name.value.trim()}`);
const apiKey = ref("");
const keySaved = ref(false);
const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") emit("close"); };
onMounted(() => window.addEventListener("keydown", closeOnEscape));
onBeforeUnmount(() => window.removeEventListener("keydown", closeOnEscape));

watch(provider, (value) => {
  name.value = value === "ollama" ? "qwen2.5-coder:7b" : "gpt-4.1-mini";
  studio.modelStatus = null;
});

async function verify() {
  if (provider.value === "openai" && apiKey.value) {
    await saveOpenAIKey(apiKey.value);
    apiKey.value = "";
    keySaved.value = true;
  }
  studio.setModel(candidate.value);
  try {
    await studio.verifyModel();
  } catch {
    // The store exposes the actionable error below.
  }
}

function save() {
  studio.setModel(candidate.value);
  emit("close");
}
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog model-dialog" role="dialog" aria-modal="true" aria-labelledby="model-title">
      <div class="dialog-heading">
        <div><span class="dialog-icon">✦</span><div><h2 id="model-title">AI model</h2><p>Choose the provider used to generate SQL.</p></div></div>
        <button aria-label="Close" @click="$emit('close')">×</button>
      </div>

      <div class="provider-options">
        <button :class="{ active: provider === 'ollama' }" @click="provider = 'ollama'">
          <span>Local</span><strong>Ollama</strong><small>Models stay on your machine.</small>
        </button>
        <button :class="{ active: provider === 'openai' }" @click="provider = 'openai'">
          <span>API</span><strong>OpenAI-compatible</strong><small>Uses your configured endpoint.</small>
        </button>
      </div>

      <label>
        <span>Model name</span>
        <input v-model="name" autocomplete="off" placeholder="qwen2.5-coder:7b" @input="studio.modelStatus = null" />
      </label>
      <label v-if="provider === 'openai'">
        <span>API key</span>
        <input v-model="apiKey" type="password" autocomplete="new-password" placeholder="Stored in your OS keyring" />
        <small v-if="keySaved">Saved securely. The key is never returned to the browser.</small>
      </label>
      <div class="environment-note">
        <template v-if="provider === 'ollama'">AskSQL discovers Ollama through <code>OLLAMA_BASE_URL</code> or localhost.</template>
        <template v-else>The API key is read from <code>OPENAI_API_KEY</code> or your OS keyring. <code>OPENAI_BASE_URL</code> remains optional.</template>
      </div>

      <div v-if="studio.modelStatus" :class="['validation', studio.modelStatus.ready ? 'success' : 'failure']">
        <span>{{ studio.modelStatus.ready ? "✓" : "!" }}</span><div>{{ studio.modelStatus.detail }}</div>
      </div>
      <div v-else-if="studio.error" class="validation failure"><span>!</span><div>{{ studio.error }}</div></div>

      <div class="dialog-actions">
        <button class="secondary-button" :disabled="!name.trim() || studio.activity === 'model'" @click="verify">
          <span v-if="studio.activity === 'model'" class="spinner" /> Test model
        </button>
        <div>
          <button class="ghost-button" @click="$emit('close')">Cancel</button>
          <button class="primary-button" :disabled="!name.trim()" @click="save">Use model</button>
        </div>
      </div>
    </section>
  </div>
</template>
