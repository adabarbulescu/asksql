<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import ConnectionDialog from "./components/ConnectionDialog.vue";
import HistoryPanel from "./components/HistoryPanel.vue";
import ModelDialog from "./components/ModelDialog.vue";
import ResultsGrid from "./components/ResultsGrid.vue";
import SchemaTree from "./components/SchemaTree.vue";
import SqlEditor from "./components/SqlEditor.vue";
import WriteReviewDialog from "./components/WriteReviewDialog.vue";
import { useStudioStore } from "./stores/studio";
import type { ConnectionProfile } from "./types";

const studio = useStudioStore();
const activeTab = ref<"results" | "messages">("results");
const sidebarTab = ref<"connections" | "history">("connections");
const connectionDialog = ref(false);
const editingConnection = ref<ConnectionProfile>();
const modelDialog = ref(false);
const deletingConnection = ref<ConnectionProfile>();
const rowCount = computed(() => studio.execution?.result?.rows.length ?? 0);

onMounted(() => studio.initialise());
watch(
  () => [studio.selectedConnection, studio.question, studio.sql],
  () => studio.persistDraft(),
);

function openAddConnection() {
  editingConnection.value = undefined;
  connectionDialog.value = true;
}

function openEditConnection() {
  if (!studio.selectedProfile) return;
  editingConnection.value = studio.selectedProfile;
  connectionDialog.value = true;
}

async function confirmDelete() {
  if (!deletingConnection.value) return;
  try {
    await studio.deleteConnection(deletingConnection.value.name);
    deletingConnection.value = undefined;
  } catch {
    // The store exposes the actionable error in the workspace.
  }
}

async function useDemo() {
  try {
    await studio.useDemo();
  } catch {
    // The store exposes the actionable error in the onboarding card.
  }
}
</script>

<template>
  <main class="studio-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">A</span><strong>AskSQL</strong><span>Studio</span></div>
      <div class="topbar-center">
        <span class="pulse" /> Local workspace
      </div>
      <button class="model-pill" @click="modelDialog = true">
        <span :class="['model-state', { ready: studio.modelStatus?.ready }]" />
        <div><small>Model</small><strong>{{ studio.model }}</strong></div>
        <i>⌄</i>
      </button>
    </header>

    <section class="workspace">
      <aside class="connections-panel">
        <div class="panel-heading">
          <div class="sidebar-tabs">
            <button :class="{ active: sidebarTab === 'connections' }" @click="sidebarTab = 'connections'">Connections</button>
            <button :class="{ active: sidebarTab === 'history' }" @click="sidebarTab = 'history'; studio.loadHistory()">History</button>
          </div>
          <div class="heading-actions"><span class="count">{{ studio.connections.length }}</span><button title="Add connection" @click="openAddConnection">＋</button></div>
        </div>
        <div v-if="sidebarTab === 'connections'" class="connections-list">
          <button
            v-for="connection in studio.connections"
            :key="connection.name"
            :class="['connection', { active: studio.selectedConnection === connection.name }]"
            @click="studio.selectConnection(connection.name)"
          >
            <span class="database-icon">◉</span>
            <span><strong>{{ connection.name }}</strong><small>{{ connection.url.startsWith('sqlite:') ? 'SQLite' : 'PostgreSQL' }}</small></span>
            <i />
          </button>
          <div v-if="!studio.connections.length && studio.activity !== 'connections'" class="no-connections">
            <span>◉</span><strong>No connections yet</strong><small>Add an existing database or explore the demo.</small>
          </div>
        </div>
        <HistoryPanel v-else />
        <div class="local-note"><span>⌂</span><div><strong>Local-first</strong><small>Your data stays on this machine.</small></div></div>
      </aside>

      <aside class="schema-panel">
        <div class="panel-heading">
          <span>Schema</span>
          <div class="heading-actions" v-if="studio.selectedProfile">
            <button title="Edit connection" @click="openEditConnection">✎</button>
            <button title="Remove connection" @click="deletingConnection = studio.selectedProfile">⌫</button>
            <button title="Refresh schema" @click="studio.selectConnection(studio.selectedConnection)">↻</button>
          </div>
        </div>
        <div v-if="studio.selectedProfile" class="schema-database">
          <strong>{{ studio.selectedProfile.name }}</strong><small>{{ studio.tables.length }} tables</small>
        </div>
        <SchemaTree :tables="studio.tables" :loading="studio.activity === 'schema'" :selected="studio.selectedTables" @preview="studio.previewTable" @toggle="studio.toggleContextTable" />
        <div v-if="studio.views.length || studio.triggers.length" class="schema-objects">
          <strong>Objects</strong>
          <span v-for="view in studio.views" :key="view.name">◫ {{ view.name }} <small>view</small></span>
          <span v-for="trigger in studio.triggers" :key="trigger.name">⚡ {{ trigger.name }} <small>trigger</small></span>
        </div>
      </aside>

      <section v-if="!studio.connections.length && studio.activity !== 'connections'" class="onboarding-panel">
        <div class="onboarding-card">
          <span class="onboarding-mark">A</span>
          <p class="eyebrow">Welcome to AskSQL Studio</p>
          <h1>Start with a database</h1>
          <p>Connect an existing SQLite file. AskSQL validates it read-only and keeps all database access on this machine.</p>
          <div class="onboarding-actions">
            <button class="primary-button large" @click="openAddConnection"><span>＋</span> Add existing database</button>
            <button class="secondary-button large" :disabled="studio.activity === 'demo'" @click="useDemo">
              <span v-if="studio.activity === 'demo'" class="spinner" /><span v-else>◇</span> Explore the demo
            </button>
          </div>
          <div class="trust-row"><span>✓ Existing files only</span><span>✓ Read-only by default</span><span>✓ No database uploads</span></div>
          <div v-if="studio.error" class="error-banner"><span>!</span>{{ studio.error }}</div>
        </div>
      </section>

      <section v-else class="main-panel">
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
            <button v-if="!studio.activeJobId" class="write-button" :disabled="studio.busy || !studio.selectedConnection || !studio.sql.trim()" @click="studio.prepareWrite">Review write</button>
            <button v-if="studio.activeJobId" class="cancel-button" @click="studio.cancelExecution">
              ■ Cancel
            </button>
            <button v-else class="run-button" :disabled="studio.busy || !studio.selectedConnection || !studio.sql.trim()" @click="studio.execute">
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
            <button @click="activeTab = 'messages'; studio.explain()">Query plan</button>
            <div v-if="studio.execution" class="execution-meta">
              <span :class="studio.execution.status">{{ studio.execution.status }}</span>
              {{ studio.execution.durationMs.toFixed(1) }} ms
              <template v-if="studio.execution.result?.truncated"> · limited to {{ studio.execution.result.limit }}</template>
              <span v-if="studio.execution.result" class="export-actions">
                <button title="Export CSV" @click="studio.exportResults('csv')">CSV</button>
                <button title="Export JSON" @click="studio.exportResults('json')">JSON</button>
                <button title="Export Markdown" @click="studio.exportResults('markdown')">MD</button>
              </span>
            </div>
          </div>
          <ResultsGrid v-if="activeTab === 'results'" :execution="studio.execution" :loading="studio.activity === 'execute'" />
          <div v-else class="messages-view">
            <template v-if="studio.queryPlan">
              <strong>Query plan</strong>
              <div v-for="(row, index) in studio.queryPlan.rows" :key="index" class="plan-row">{{ row.join(' · ') }}</div>
            </template>
            <template v-else>{{ studio.execution?.error || "No messages for this query." }}</template>
          </div>
        </section>
      </section>
    </section>

    <ConnectionDialog
      v-if="connectionDialog"
      :profile="editingConnection"
      @close="connectionDialog = false"
      @saved="connectionDialog = false"
    />
    <ModelDialog v-if="modelDialog" @close="modelDialog = false" />
    <WriteReviewDialog v-if="studio.writeReview" />
    <div v-if="deletingConnection" class="modal-backdrop" @mousedown.self="deletingConnection = undefined">
      <section class="dialog confirm-dialog" role="alertdialog" aria-modal="true">
        <div class="danger-mark">⌫</div>
        <h2>Remove {{ deletingConnection.name }}?</h2>
        <p>The saved profile will be removed. The SQLite database file will not be changed or deleted.</p>
        <div class="dialog-actions right">
          <button class="ghost-button" @click="deletingConnection = undefined">Cancel</button>
          <button class="danger-button" :disabled="studio.activity === 'save-connection'" @click="confirmDelete">Remove profile</button>
        </div>
      </section>
    </div>
  </main>
</template>
