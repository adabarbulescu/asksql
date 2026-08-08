<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import ConnectionDialog from "./components/ConnectionDialog.vue";
import AnalysisWorkspace from "./components/AnalysisWorkspace.vue";
import BusinessModelPanel from "./components/BusinessModelPanel.vue";
import HistoryPanel from "./components/HistoryPanel.vue";
import ModelDialog from "./components/ModelDialog.vue";
import ParameterForm from "./components/ParameterForm.vue";
import ResultsGrid from "./components/ResultsGrid.vue";
import SchemaTree from "./components/SchemaTree.vue";
import SavedQueriesPanel from "./components/SavedQueriesPanel.vue";
import SqlEditor from "./components/SqlEditor.vue";
import WriteReviewDialog from "./components/WriteReviewDialog.vue";
import { useStudioStore } from "./stores/studio";
import type { ConnectionProfile } from "./types";
import type { SavedQueryParameter, SavedQueryParameterType } from "./types";

const studio = useStudioStore();
const workspaceMode = ref<"analysis" | "sql">("analysis");
const activeTab = ref<"results" | "messages">("results");
const sidebarTab = ref<"connections" | "history" | "library">("connections");
const connectionDialog = ref(false);
const editingConnection = ref<ConnectionProfile>();
const modelDialog = ref(false);
const businessModelDialog = ref(false);
const deletingConnection = ref<ConnectionProfile>();
const rowCount = computed(() => studio.execution?.result?.rows.length ?? 0);
const savedForActive = computed(() => studio.savedQueries.find((item) => item.source_document_id === studio.activeDocumentId));
const question = computed({
  get: () => studio.activeDocument?.question ?? "",
  set: (value: string) => {
    if (!studio.activeDocument) return;
    studio.activeDocument.question = value;
    if (studio.activeDocument.lifecycle_state !== "running") studio.activeDocument.lifecycle_state = "draft";
  },
});
const sql = computed({
  get: () => studio.activeDocument?.edited_sql ?? "",
  set: (value: string) => {
    if (!studio.activeDocument) return;
    studio.activeDocument.edited_sql = value;
    if (studio.activeDocument.semantic_plan && value !== studio.activeDocument.generated_sql) {
      studio.activeDocument.semantic_plan = null;
      studio.activeDocument.semantic_model_id = null;
      studio.generationMode = "";
      studio.semanticTrace = [];
    }
    if (studio.activeDocument.lifecycle_state !== "running") studio.activeDocument.lifecycle_state = "draft";
  },
});

onMounted(() => studio.initialise());
watch(
  () => [studio.selectedConnection, question.value, sql.value, studio.selectedTables],
  () => studio.persistDraft(),
  { deep: true },
);

async function renameDocument(identifier: string, current: string) {
  const title = window.prompt("Query name", current)?.trim();
  if (title && title !== current) await studio.renameDocument(identifier, title);
}

async function saveQuery(saveAs = false) {
  if (!studio.activeDocument) return;
  const existing = saveAs ? undefined : savedForActive.value;
  const name = window.prompt("Saved query name", existing?.name ?? studio.activeDocument.title)?.trim();
  if (!name) return;
  const description = window.prompt("Description", existing?.description ?? "") ?? "";
  const folder = window.prompt("Folder (optional)", existing?.folder ?? "")?.trim() || undefined;
  const tags = (window.prompt("Tags, separated by commas", existing?.tags.join(", ") ?? "") ?? "")
    .split(",").map((tag) => tag.trim()).filter(Boolean);
  const names = [...sql.value.matchAll(/(?<!:):([A-Za-z_][A-Za-z0-9_]*)/g)].map((match) => match[1])
    .filter((value, index, values) => values.indexOf(value) === index);
  const parameters: SavedQueryParameter[] = [];
  for (const parameterName of names) {
    const prior = existing?.parameters.find((parameter) => parameter.name === parameterName);
    const dataType = (window.prompt(
      `Type for :${parameterName} (text, integer, decimal, boolean, date, datetime)`, prior?.data_type ?? "text",
    )?.trim() || "text") as SavedQueryParameterType;
    const defaultValue = window.prompt(`Default value for :${parameterName} (optional)`, String(prior?.default_value ?? ""));
    const required = window.confirm(`Is :${parameterName} required?`);
    const sensitive = window.confirm(`Is :${parameterName} sensitive? Sensitive values are never persisted.`);
    const parameterDescription = window.prompt(`Label or description for :${parameterName}`, prior?.description ?? parameterName) ?? parameterName;
    parameters.push({ name: parameterName, data_type: dataType, required,
      default_value: defaultValue || null, description: parameterDescription, sensitive });
  }
  await studio.saveActiveQuery({ name, description, folder, tags, parameters }, saveAs);
}

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
        <span :class="['pulse', { ready: studio.setupStatus?.ready }]" /> {{ studio.setupStatus?.ready ? "Ready" : "Setup needed" }}
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
            <button :class="{ active: sidebarTab === 'library' }" @click="sidebarTab = 'library'; studio.loadSavedQueries()">Library</button>
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
        <HistoryPanel v-else-if="sidebarTab === 'history'" />
        <SavedQueriesPanel v-else />
        <div class="local-note"><span>⌂</span><div><strong>Local-first</strong><small>Your data stays on this machine.</small></div></div>
      </aside>

      <aside class="schema-panel">
        <div class="panel-heading">
          <span>Schema</span>
          <div class="heading-actions" v-if="studio.selectedProfile">
            <button title="Business model" @click="businessModelDialog = true">◇</button>
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
            <button class="secondary-button large" @click="modelDialog = true"><span>✦</span> Configure model</button>
          </div>
          <div v-if="studio.setupStatus?.nextSteps.length" class="setup-steps">
            <strong>Next steps</strong>
            <span v-for="step in studio.setupStatus.nextSteps" :key="step">{{ step }}</span>
          </div>
          <div class="trust-row"><span>✓ Existing files only</span><span>✓ Read-only by default</span><span>✓ No database uploads</span></div>
          <div v-if="studio.error" class="error-banner"><span>!</span>{{ studio.error }}</div>
          <ParameterForm />
        </div>
      </section>

      <AnalysisWorkspace v-else-if="workspaceMode === 'analysis'" @open-sql="workspaceMode = 'sql'" @open-model="businessModelDialog = true" />

      <section v-else class="main-panel">
        <nav class="query-tabs" aria-label="Open queries">
          <button class="analysis-return" title="Back to Analysis" @click="workspaceMode = 'analysis'">✦ Analysis</button>
          <button
            v-for="document in studio.documents"
            :key="document.id"
            :class="['query-tab', { active: document.id === studio.activeDocumentId }]"
            @click="studio.activateDocument(document.id)"
            @dblclick="renameDocument(document.id, document.title)"
          >
            <span :class="['document-state', document.lifecycle_state]" />
            <span class="query-tab-title">{{ document.title }}</span>
            <small>{{ document.connection }}</small>
            <i title="Close query" @click.stop="studio.closeDocument(document.id)">×</i>
          </button>
          <button class="new-query-tab" title="New query" @click="studio.newDocument">＋</button>
        </nav>
        <div class="conversation">
          <div class="welcome-copy">
            <span class="spark">✦</span>
            <div><strong>What do you want to learn from your data?</strong><small>Ask naturally. You will always review the SQL before it runs.</small></div>
          </div>
          <div v-if="studio.semanticModels.length" class="semantic-context-bar">
            <span>◇ Semantic model</span>
            <select v-model="studio.selectedSemanticModelId" @change="studio.loadAnalysisLibrary()">
              <option value="">Disabled</option>
              <option v-for="model in studio.semanticModels" :key="model.id" :value="model.id">{{ model.name }}</option>
            </select>
            <button @click="businessModelDialog = true">Edit model</button>
          </div>
          <div class="question-box">
            <textarea
              v-model="question"
              rows="2"
              :disabled="!studio.selectedConnection"
              placeholder="Which customers generated the most revenue last month?"
              @keydown.ctrl.enter.prevent="studio.generate"
            />
            <div class="question-actions">
              <span>Ctrl ↵ to generate</span>
              <button :disabled="studio.busy || !question.trim() || !studio.selectedConnection" @click="studio.generate">
                <span v-if="studio.activity === 'generate'" class="spinner" />
                <span v-else>✦</span> Generate SQL
              </button>
            </div>
          </div>
          <div v-if="studio.error" class="error-banner"><span>!</span>{{ studio.error }}</div>
          <div v-if="studio.generationMode" :class="['generation-mode', studio.generationMode]">
            <strong>{{ studio.generationMode === 'semantic' ? '◇ Semantic compilation' : '✦ Free-form SQL' }}</strong>
            <span v-if="studio.generationMode === 'semantic'">Resolved through {{ studio.semanticTrace.length }} audited definitions.</span>
            <span v-else>No exact semantic metric matched; the model received the business vocabulary as context.</span>
          </div>
        </div>

        <section class="query-panel">
          <div class="query-heading">
            <div><span :class="['status-dot', studio.activeDocument?.lifecycle_state]" /><strong>SQL review</strong><small>{{ studio.activeDocument?.lifecycle_state }} · Read-only execution</small></div>
            <button class="save-query-button" :disabled="!sql.trim()" @click="saveQuery(false)">{{ savedForActive ? "Save" : "Save query" }}</button>
            <button v-if="savedForActive" class="save-query-button" :disabled="!sql.trim()" @click="saveQuery(true)">Save as</button>
            <button v-if="!studio.activeJobId" class="write-button" :disabled="studio.busy || !studio.selectedConnection || !sql.trim()" @click="studio.prepareWrite">Review write</button>
            <button v-if="studio.activeJobId" class="cancel-button" @click="studio.cancelExecution">
              ■ Cancel
            </button>
            <button v-else class="run-button" :disabled="studio.busy || !studio.selectedConnection || !sql.trim()" @click="studio.execute">
              <span v-if="studio.activity === 'execute'" class="spinner dark" />
              <span v-else>▶</span> Run query
            </button>
          </div>
          <SqlEditor v-model="sql" />
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
            <div v-else-if="studio.activeDocument?.execution_status" class="execution-meta">
              <span :class="studio.activeDocument.execution_status">{{ studio.activeDocument.execution_status }}</span>
              <template v-if="studio.activeDocument.duration_ms !== null">{{ studio.activeDocument.duration_ms.toFixed(1) }} ms</template>
              <template v-if="studio.activeDocument.row_count !== null"> · {{ studio.activeDocument.row_count }} rows</template>
            </div>
          </div>
          <ResultsGrid v-if="activeTab === 'results'" :execution="studio.execution" :loading="studio.activity === 'execute'" />
          <div v-else class="messages-view">
            <template v-if="studio.semanticTrace.length">
              <strong>Semantic plan</strong>
              <div v-for="item in studio.semanticTrace" :key="`${item.kind}-${item.name}`" class="semantic-trace-row">
                <span>{{ item.kind }}</span><strong>{{ item.name }}</strong><code>{{ item.sql }}</code>
              </div>
            </template>
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
    <BusinessModelPanel v-if="businessModelDialog" @close="businessModelDialog = false" />
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
