<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

import { useStudioStore } from "../stores/studio";

const studio = useStudioStore();
const acknowledgement = ref("");
const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") studio.writeReview = null; };
onMounted(() => window.addEventListener("keydown", closeOnEscape));
onBeforeUnmount(() => window.removeEventListener("keydown", closeOnEscape));
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="studio.writeReview = null">
    <section class="dialog write-dialog" role="alertdialog" aria-modal="true" aria-labelledby="write-title">
      <div class="dialog-heading">
        <div><span class="danger-mark">!</span><div><h2 id="write-title">Confirm database write</h2><p>This changes data and cannot be undone by AskSQL.</p></div></div>
        <button aria-label="Close" @click="studio.writeReview = null">×</button>
      </div>
      <div class="write-content">
        <div class="write-facts"><span>{{ studio.writeReview?.statement }}</span><span>{{ studio.selectedConnection }}</span><span>Expires {{ studio.writeReview?.expiresAt }}</span></div>
        <pre>{{ studio.sql }}</pre>
        <label>
          <span>Type <strong>{{ studio.selectedConnection }}</strong> to confirm</span>
          <input v-model="acknowledgement" autofocus autocomplete="off" />
        </label>
      </div>
      <div class="dialog-actions right">
        <button class="ghost-button" @click="studio.writeReview = null">Cancel</button>
        <button class="danger-button" :disabled="acknowledgement !== studio.selectedConnection" @click="studio.commitWrite">Execute write</button>
      </div>
    </section>
  </div>
</template>
