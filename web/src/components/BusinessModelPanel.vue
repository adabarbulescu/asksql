<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { compileSemanticModel } from "../api";
import { useStudioStore } from "../stores/studio";
import type { SemanticModel, SemanticModelInput, SemanticSuggestion } from "../types";

const emit = defineEmits<{ close: [] }>();
const studio = useStudioStore();
const editing = ref<SemanticModel | null>(null);
const section = ref<"metrics" | "dimensions" | "relationships">("metrics");
const previewSql = ref("");
const current = computed(() => studio.semanticModels.find((item) => item.id === studio.selectedSemanticModelId));

watch(current, (value) => { editing.value = value ? clone(value) : null; previewSql.value = ""; }, { immediate: true });

function clone(value: SemanticModel): SemanticModel {
  return JSON.parse(JSON.stringify(value)) as SemanticModel;
}

function newModel() {
  studio.semanticDraft = null;
  studio.semanticReadiness = null;
  editing.value = {
    id: "", name: "Business model", description: "", connection_hint: studio.selectedConnection,
    entities: [], metrics: [], dimensions: [], relationships: [], created_at: "", updated_at: "",
  };
}

function inputModel(): SemanticModelInput | null {
  if (!editing.value) return null;
  return {
    name: editing.value.name,
    description: editing.value.description,
    connection_hint: editing.value.connection_hint,
    entities: editing.value.entities,
    metrics: editing.value.metrics,
    dimensions: editing.value.dimensions,
    relationships: editing.value.relationships,
  };
}

async function suggestModel() {
  const draft = await studio.proposeBusinessModel();
  if (!draft) return;
  editing.value = { ...cloneInput(draft.model), id: "", created_at: "", updated_at: "" };
  section.value = "metrics";
  previewSql.value = "";
}

function cloneInput(value: SemanticModelInput): SemanticModelInput {
  return JSON.parse(JSON.stringify(value)) as SemanticModelInput;
}

function suggestion(path: string): SemanticSuggestion | undefined {
  return studio.semanticDraft?.suggestions.find((item) => item.path === path);
}

async function checkReadiness() {
  const payload = inputModel();
  if (payload) await studio.checkBusinessModel(payload);
}

function tableColumns(tableName: string) {
  return studio.tables.find((table) => table.name === tableName)?.columns ?? [];
}

function entityColumns(entityName: string) {
  const entity = editing.value?.entities.find((item) => item.name === entityName);
  return entity ? tableColumns(entity.source_table) : [];
}

function addEntity() {
  if (!editing.value) return;
  const table = studio.tables.find((item) => !editing.value?.entities.some((entity) => entity.source_table === item.name));
  if (!table) return;
  const name = table.name.replace(/[^A-Za-z0-9_]/g, "_").toLowerCase();
  editing.value.entities.push({ name, source_table: table.name,
    primary_key: table.columns.find((column) => column.primaryKey)?.name ?? table.columns[0]?.name ?? "id", description: "" });
}

function addMetric() {
  const entity = editing.value?.entities[0];
  if (!editing.value || !entity) return;
  editing.value.metrics.push({ name: `metric_${editing.value.metrics.length + 1}`, label: "New metric", description: "",
    entity: entity.name, aggregation: "sum", expression: entityColumns(entity.name)[0]?.name ?? "id", filters: [], format: "number" });
}

function addDimension() {
  const entity = editing.value?.entities[0];
  if (!editing.value || !entity) return;
  editing.value.dimensions.push({ name: `dimension_${editing.value.dimensions.length + 1}`, label: "New dimension",
    description: "", entity: entity.name, expression: entityColumns(entity.name)[0]?.name ?? "id",
    data_type: "text", time_granularities: [] });
}

function addRelationship() {
  if (!editing.value || editing.value.entities.length < 2) return;
  const [from, to] = editing.value.entities;
  editing.value.relationships.push({ name: `${from.name}_to_${to.name}`, from_entity: from.name, to_entity: to.name,
    from_column: entityColumns(from.name)[0]?.name ?? "id", to_column: to.primary_key,
    join_type: "left", cardinality: "many_to_one" });
}

async function save() {
  const payload = inputModel();
  if (!editing.value || !payload) return;
  const saved = await studio.saveSemanticModel(payload, editing.value.id || undefined);
  editing.value = clone(saved);
}

async function remove() {
  if (!editing.value?.id || !window.confirm(`Delete ${editing.value.name}?`)) return;
  await studio.removeSemanticModel(editing.value.id);
  editing.value = null;
}

async function preview() {
  if (!editing.value?.id || !editing.value.metrics.length) return;
  try {
    const compiled = await compileSemanticModel(editing.value.id, editing.value.connection_hint,
      [editing.value.metrics[0].name], []);
    previewSql.value = compiled.sql;
  } catch (error) {
    studio.error = error instanceof Error ? error.message : "Semantic preview failed";
  }
}
</script>

<template>
  <div class="business-model-backdrop" @mousedown.self="emit('close')">
    <section class="business-model-dialog" role="dialog" aria-modal="true" aria-label="Business model editor">
      <header>
        <div><span class="semantic-mark">◇</span><div><strong>Business Model</strong><small>Reusable metrics, dimensions and joins</small></div></div>
        <button class="ghost-button" @click="emit('close')">Close</button>
      </header>
      <aside>
        <button class="primary-button" @click="newModel">＋ New model</button>
        <button class="secondary-button semantic-suggest-button" :disabled="studio.activity === 'semantic'" @click="suggestModel">
          <span v-if="studio.activity === 'semantic'" class="spinner" />◇ Suggest from schema
        </button>
        <button v-for="model in studio.semanticModels" :key="model.id"
          :class="['model-list-item', { active: model.id === editing?.id }]"
          @click="studio.selectSemanticModel(model.id)">
          <strong>{{ model.name }}</strong><small>{{ model.metrics.length }} metrics · {{ model.dimensions.length }} dimensions</small>
        </button>
      </aside>
      <main v-if="editing">
        <section v-if="studio.semanticDraft" class="semantic-draft-banner">
          <div><strong>Review the proposed model</strong><p>Nothing is saved until you confirm it. Suggestions use schema metadata only—never rows or an LLM.</p></div>
          <span>{{ studio.semanticDraft.suggestions.length }} suggestions</span>
        </section>
        <div v-if="studio.semanticDraft?.warnings.length" class="semantic-warning-list">
          <span v-for="warning in studio.semanticDraft.warnings" :key="warning">{{ warning }}</span>
        </div>
        <div class="model-basics">
          <label><span>Name</span><input v-model="editing.name" /></label>
          <label><span>Description</span><input v-model="editing.description" placeholder="Business definitions for this database" /></label>
        </div>
        <section class="entity-strip">
          <div class="section-title"><strong>Entities</strong><button @click="addEntity">＋ Add table</button></div>
          <article v-for="(entity, index) in editing.entities" :key="index">
            <input v-model="entity.name" aria-label="Entity name" />
            <select v-model="entity.source_table"><option v-for="table in studio.tables" :key="table.name">{{ table.name }}</option></select>
            <select v-model="entity.primary_key"><option v-for="column in tableColumns(entity.source_table)" :key="column.name">{{ column.name }}</option></select>
            <button title="Remove entity" @click="editing.entities.splice(index, 1)">×</button>
            <small v-if="suggestion(`entities.${entity.name}`)" class="semantic-reason">
              {{ suggestion(`entities.${entity.name}`)?.reason }} · {{ suggestion(`entities.${entity.name}`)?.confidence }} confidence
            </small>
          </article>
        </section>
        <nav class="semantic-tabs">
          <button v-for="item in (['metrics', 'dimensions', 'relationships'] as const)" :key="item"
            :class="{ active: section === item }" @click="section = item">{{ item }}</button>
        </nav>
        <section v-if="section === 'metrics'" class="semantic-definition-list">
          <article v-for="(metric, index) in editing.metrics" :key="index" class="semantic-card">
            <div class="semantic-card-heading"><input v-model="metric.label" aria-label="Metric label" />
              <button @click="editing.metrics.splice(index, 1)">×</button></div>
            <div class="definition-grid">
              <label><span>Identifier</span><input v-model="metric.name" /></label>
              <label><span>Entity</span><select v-model="metric.entity"><option v-for="entity in editing.entities" :key="entity.name">{{ entity.name }}</option></select></label>
              <label><span>Aggregation</span><select v-model="metric.aggregation"><option>sum</option><option>count</option><option>count_distinct</option><option>average</option><option>minimum</option><option>maximum</option></select></label>
              <label><span>Column</span><select v-model="metric.expression"><option v-for="column in entityColumns(metric.entity)" :key="column.name">{{ column.name }}</option></select></label>
            </div>
            <label><span>Description</span><input v-model="metric.description" /></label>
            <small v-if="suggestion(`metrics.${metric.name}`)" class="semantic-reason">
              {{ suggestion(`metrics.${metric.name}`)?.reason }} · {{ suggestion(`metrics.${metric.name}`)?.confidence }} confidence
            </small>
            <div class="filter-row" v-for="(filter, filterIndex) in metric.filters" :key="filterIndex">
              <select v-model="filter.column"><option v-for="column in entityColumns(metric.entity)" :key="column.name">{{ column.name }}</option></select>
              <select v-model="filter.operator"><option>eq</option><option>neq</option><option>gt</option><option>gte</option><option>lt</option><option>lte</option></select>
              <input v-model="filter.value" placeholder="Value" /><button @click="metric.filters.splice(filterIndex, 1)">×</button>
            </div>
            <button class="inline-add" @click="metric.filters.push({ column: entityColumns(metric.entity)[0]?.name ?? 'id', operator: 'eq', value: '' })">＋ Default filter</button>
          </article>
          <button class="definition-add" :disabled="!editing.entities.length" @click="addMetric">＋ Add metric</button>
        </section>
        <section v-else-if="section === 'dimensions'" class="semantic-definition-list">
          <article v-for="(dimension, index) in editing.dimensions" :key="index" class="semantic-card">
            <div class="semantic-card-heading"><input v-model="dimension.label" aria-label="Dimension label" /><button @click="editing.dimensions.splice(index, 1)">×</button></div>
            <div class="definition-grid">
              <label><span>Identifier</span><input v-model="dimension.name" /></label>
              <label><span>Entity</span><select v-model="dimension.entity"><option v-for="entity in editing.entities" :key="entity.name">{{ entity.name }}</option></select></label>
              <label><span>Column</span><select v-model="dimension.expression"><option v-for="column in entityColumns(dimension.entity)" :key="column.name">{{ column.name }}</option></select></label>
              <label><span>Type</span><select v-model="dimension.data_type"><option>text</option><option>integer</option><option>decimal</option><option>boolean</option><option>date</option><option>datetime</option></select></label>
            </div>
            <label><span>Time grains (comma-separated)</span><input :value="dimension.time_granularities.join(', ')" @change="dimension.time_granularities = ($event.target as HTMLInputElement).value.split(',').map(item => item.trim()).filter(Boolean)" /></label>
            <small v-if="suggestion(`dimensions.${dimension.name}`)" class="semantic-reason">
              {{ suggestion(`dimensions.${dimension.name}`)?.reason }} · {{ suggestion(`dimensions.${dimension.name}`)?.confidence }} confidence
            </small>
          </article>
          <button class="definition-add" :disabled="!editing.entities.length" @click="addDimension">＋ Add dimension</button>
        </section>
        <section v-else class="semantic-definition-list">
          <article v-for="(relationship, index) in editing.relationships" :key="index" class="semantic-card">
            <div class="semantic-card-heading"><input v-model="relationship.name" aria-label="Relationship name" /><button @click="editing.relationships.splice(index, 1)">×</button></div>
            <div class="relationship-grid">
              <select v-model="relationship.from_entity"><option v-for="entity in editing.entities" :key="entity.name">{{ entity.name }}</option></select>
              <select v-model="relationship.from_column"><option v-for="column in entityColumns(relationship.from_entity)" :key="column.name">{{ column.name }}</option></select>
              <span>→</span>
              <select v-model="relationship.to_entity"><option v-for="entity in editing.entities" :key="entity.name">{{ entity.name }}</option></select>
              <select v-model="relationship.to_column"><option v-for="column in entityColumns(relationship.to_entity)" :key="column.name">{{ column.name }}</option></select>
              <select v-model="relationship.cardinality"><option>many_to_one</option><option>one_to_many</option><option>one_to_one</option></select>
            </div>
            <small v-if="suggestion(`relationships.${relationship.name}`)" class="semantic-reason">
              {{ suggestion(`relationships.${relationship.name}`)?.reason }} · {{ suggestion(`relationships.${relationship.name}`)?.confidence }} confidence
            </small>
          </article>
          <button class="definition-add" :disabled="editing.entities.length < 2" @click="addRelationship">＋ Add relationship</button>
        </section>
        <section v-if="studio.semanticReadiness" class="semantic-readiness" :class="{ ready: studio.semanticReadiness.ready }">
          <header><div><strong>{{ studio.semanticReadiness.ready ? 'Ready for analysis' : 'Review required' }}</strong>
            <small>Structural preflight and bounded read-only trust checks</small></div>
            <span>{{ studio.semanticReadiness.validation_results?.length ?? 0 }} local checks run</span></header>
          <div class="readiness-checks">
            <span v-for="check in studio.semanticReadiness.checks" :key="check.code" :class="check.status">
              {{ check.status === 'passed' ? '✓' : '!' }} {{ check.message }}
            </span>
          </div>
          <div class="workflow-readiness">
            <div v-for="workflow in studio.semanticReadiness.workflows" :key="workflow.workflow">
              <strong>{{ workflow.workflow.replaceAll('_', ' ') }}</strong>
              <small>{{ workflow.eligible ? 'Eligible' : workflow.missing.join(' ') }}</small>
            </div>
          </div>
          <div v-if="studio.semanticReadiness.validation_results?.length" class="validation-results">
            <article v-for="result in studio.semanticReadiness.validation_results" :key="result.id" :class="result.status">
              <span>{{ result.status === 'passed' ? '✓' : '!' }}</span>
              <div><strong>{{ result.title }}</strong><small>{{ result.message }}</small></div>
              <em>{{ result.status }}</em>
            </article>
          </div>
        </section>
        <pre v-if="previewSql" class="semantic-preview">{{ previewSql }}</pre>
        <footer><button v-if="editing.id" class="danger-text" @click="remove">Delete model</button><span />
          <button class="secondary-button" :disabled="studio.activity === 'semantic'" @click="checkReadiness">Check readiness</button>
          <button v-if="editing.id" class="secondary-button" :disabled="!editing.metrics.length" @click="preview">Preview SQL</button>
          <button class="primary-button" :disabled="studio.activity === 'semantic'" @click="save">Save and validate</button></footer>
      </main>
      <main v-else class="empty-semantic"><span>◇</span><strong>Define the language of your data</strong><p>Review a schema-only proposal or build a model manually. Nothing is saved until you confirm it.</p><div><button class="primary-button" :disabled="studio.activity === 'semantic'" @click="suggestModel">Suggest from schema</button><button class="secondary-button" @click="newModel">Build manually</button></div></main>
    </section>
  </div>
</template>
