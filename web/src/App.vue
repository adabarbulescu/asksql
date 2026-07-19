<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import ResultsGrid from "./components/ResultsGrid.vue";
import SchemaTree from "./components/SchemaTree.vue";
import SqlEditor from "./components/SqlEditor.vue";
import { useStudioStore } from "./stores/studio";

const studio = useStudioStore();
const activeTab = ref<"results" | "messages">("results");
const rowCount = computed(() => studio.execution?.result?.rows.length ?? 0);

onMounted(() => studio.initialise());
</script>

<template>
  <main class="studio-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">A</span><strong>AskSQL</strong><span>Studio</span></div>
      <div class="topbar-center">
        <span class="pulse" /> Local workspace
      </div>
      <div class="model-pill"><span>Model</span><input v-model="studio.model" aria-label="Model" /></div>
    </header>

    <section class="workspace">
      <aside class="connections-panel">
        <div class="panel-heading"><span>Connections</span><span class="count">{{ studio.connections.length }}</span></div>
        <div class="connections-list">
          <button
            v-for="connection in studio.connections"
            :key="connection.name"
            :class="['connection', { active: studio.selectedConnection === connection.name }]"
            @click="studio.selectConnection(connection.name)"
          >
            <span class="database-icon">◉</span>
            <span><strong>{{ connection.name }}</strong><small>SQLite</small></span>
            <i />
          </button>
          <div v-if="!studio.connections.length && studio.activity !== 'connections'" class="no-connections">
            <span>＋</span><strong>No connections yet</strong>
            <code>asksql connections add local<br />--url sqlite://app.db</code>
          </div>
        </div>
        <div class="local-note"><span>⌂</span><div><strong>Local-first</strong><small>Your data stays on this machine.</small></div></div>
      </aside>

      <aside class="schema-panel">
        <div class="panel-heading"><span>Schema</span><button title="Refresh schema" @click="studio.selectedConnection && studio.selectConnection(studio.selectedConnection)">↻</button></div>
        <div v-if="studio.selectedProfile" class="schema-database">
          <strong>{{ studio.selectedProfile.name }}</strong><small>{{ studio.tables.length }} tables</small>
        </div>
        <SchemaTree :tables="studio.tables" :loading="studio.activity === 'schema'" @preview="studio.previewTable" />
      </aside>

      <section class="main-panel">
        <div class="conversation">
          <div class="welcome-copy">
            <span class="spark">✦</span>
            <div><strong>What do you want to learn from your data?</strong><small>Ask naturally. You will always review the SQL before it runs.</small></div>
          </div>
          <div class="question-box">
            <textarea
              v-model="studio.question"
              rows="2"
              :disabled="!studio.selectedConnection"
              placeholder="Which customers generated the most revenue last month?"
              @keydown.ctrl.enter.prevent="studio.generate"
            />
            <div class="question-actions">
              <span>Ctrl ↵ to generate</span>
              <button :disabled="studio.busy || !studio.question.trim() || !studio.selectedConnection" @click="studio.generate">
                <span v-if="studio.activity === 'generate'" class="spinner" />
                <span v-else>✦</span> Generate SQL
              </button>
            </div>
          </div>
          <div v-if="studio.error" class="error-banner"><span>!</span>{{ studio.error }}</div>
        </div>

        <section class="query-panel">
          <div class="query-heading">
            <div><span class="status-dot" /><strong>SQL review</strong><small>Read-only execution</small></div>
            <button class="run-button" :disabled="studio.busy || !studio.selectedConnection || !studio.sql.trim()" @click="studio.execute">
              <span v-if="studio.activity === 'execute'" class="spinner dark" />
              <span v-else>▶</span> Run query
            </button>
          </div>
          <SqlEditor v-model="studio.sql" />
        </section>

        <section class="results-panel">
          <div class="result-tabs">
            <button :class="{ active: activeTab === 'results' }" @click="activeTab = 'results'">Results <span v-if="studio.execution?.result">{{ rowCount }}</span></button>
            <button :class="{ active: activeTab === 'messages' }" @click="activeTab = 'messages'">Messages</button>
            <div v-if="studio.execution" class="execution-meta">
              <span :class="studio.execution.status">{{ studio.execution.status }}</span>
              {{ studio.execution.durationMs.toFixed(1) }} ms
              <template v-if="studio.execution.result?.truncated"> · limited to {{ studio.execution.result.limit }}</template>
            </div>
          </div>
          <ResultsGrid v-if="activeTab === 'results'" :execution="studio.execution" :loading="studio.activity === 'execute'" />
          <div v-else class="messages-view">{{ studio.execution?.error || "No messages for this query." }}</div>
        </section>
      </section>
    </section>
  </main>
</template>
