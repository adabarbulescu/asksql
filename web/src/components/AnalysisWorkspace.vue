<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { useStudioStore } from "../stores/studio";
import type { AnalysisTemplate } from "../types";
import AnalysisChart from "./AnalysisChart.vue";

defineEmits<{ openSql: []; openModel: [] }>();
const studio = useStudioStore();
const configuring = ref(false);
const currentStart = ref(periods().currentStart);
const currentEnd = ref(periods().currentEnd);
const previousStart = ref(periods().previousStart);
const previousEnd = ref(periods().previousEnd);
const metricName = ref("");
const timeDimensionName = ref("");
const componentMetricName = ref("");
const sliceDimensionNames = ref<string[]>([]);
const selectedModel = computed(() => studio.semanticModels.find((item) => item.id === studio.selectedSemanticModelId));
const metricOptions = computed(() => selectedModel.value?.metrics ?? []);
const timeDimensionOptions = computed(() => selectedModel.value?.dimensions
  .filter((item) => item.time_granularities.includes("month")) ?? []);
const sliceDimensionOptions = computed(() => selectedModel.value?.dimensions
  .filter((item) => !item.time_granularities.length) ?? []);
const componentMetricOptions = computed(() => metricOptions.value.filter((item) => item.name !== metricName.value));
const activeTemplate = computed(() => studio.analysisTemplates.find((item) => item.id === "metric_change_investigation")
  ?? studio.analysisTemplates.find((item) => item.id === "revenue_investigation")
  ?? studio.analysisTemplates[0]);
const genericTemplate = computed(() => activeTemplate.value?.id === "metric_change_investigation");
const canLaunch = computed(() => !genericTemplate.value || Boolean(metricName.value && timeDimensionName.value));
const run = computed(() => studio.activeAnalysisRun);
const terminal = computed(() => run.value && !["planning", "running"].includes(run.value.state));
const completedSteps = computed(() => run.value?.steps.filter((item) => item.state === "completed").length ?? 0);

watch(selectedModel, (model) => {
  metricName.value = model?.metrics[0]?.name ?? "";
  timeDimensionName.value = model?.dimensions.find((item) => item.time_granularities.includes("month"))?.name ?? "";
  componentMetricName.value = "";
  sliceDimensionNames.value = [];
}, { immediate: true });

async function launch(template: AnalysisTemplate) {
  configuring.value = false;
  studio.activeAnalysisRun = null;
  await studio.runAnalysis(template, {
    current_start: currentStart.value, current_end: currentEnd.value,
    previous_start: previousStart.value, previous_end: previousEnd.value,
  }, genericTemplate.value ? {
    metric_name: metricName.value,
    time_dimension_name: timeDimensionName.value,
    component_metric_name: componentMetricName.value || undefined,
    slice_dimension_names: sliceDimensionNames.value,
  } : {});
}

function toggleSlice(name: string) {
  if (sliceDimensionNames.value.includes(name)) {
    sliceDimensionNames.value = sliceDimensionNames.value.filter((item) => item !== name);
  } else if (sliceDimensionNames.value.length < 3) {
    sliceDimensionNames.value = [...sliceDimensionNames.value, name];
  }
}

function newAnalysis() {
  studio.activeAnalysisRun = null;
  configuring.value = false;
}

function periods() {
  const now = new Date();
  const currentEndDate = new Date(now.getFullYear(), now.getMonth(), 1);
  const currentStartDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const previousStartDate = new Date(now.getFullYear(), now.getMonth() - 2, 1);
  const iso = (value: Date) => value.toISOString().slice(0, 10);
  return { currentStart: iso(currentStartDate), currentEnd: iso(currentEndDate),
    previousStart: iso(previousStartDate), previousEnd: iso(currentStartDate) };
}
</script>

<template>
  <section class="analysis-workspace">
    <header class="analysis-toolbar">
      <div><span class="analysis-mark">✦</span><strong>Analysis</strong><small>Business questions, executed with semantic evidence</small></div>
      <div>
        <button class="ghost-button" @click="$emit('openSql')">SQL Workbench</button>
        <button v-if="run" class="secondary-button" @click="newAnalysis">＋ New analysis</button>
      </div>
    </header>

    <div v-if="!run" class="analysis-catalog">
      <div class="analysis-hero">
        <p class="eyebrow">AskSQL Analysis Engine</p>
        <h1>What do you want to understand?</h1>
        <p>Choose a governed workflow. AskSQL plans the semantic queries, executes them, and keeps every conclusion linked to evidence.</p>
      </div>

      <div v-if="!studio.selectedSemanticModelId" class="analysis-prerequisite">
        <span>◇</span><div><strong>A Business Model is required</strong><p>Review a schema-based proposal to define a metric and monthly time dimension.</p></div>
        <button class="primary-button" @click="$emit('openModel')">Create from schema →</button>
      </div>
      <article v-else-if="activeTemplate" :class="['analysis-template-card', { unavailable: !activeTemplate.available }]">
        <div class="template-icon">↘</div>
        <div class="template-copy">
          <span>DIAGNOSTIC WORKFLOW</span>
          <h2>{{ activeTemplate.name }}</h2>
          <p>{{ activeTemplate.description }}</p>
          <small>{{ activeTemplate.estimated_queries }} governed semantic queries · evidence retained · follow-up enabled</small>
          <em v-if="!activeTemplate.available">{{ activeTemplate.unavailable_reason }}</em>
        </div>
        <div class="template-actions">
          <button v-if="!activeTemplate.available" class="secondary-button" @click="$emit('openModel')">Review model</button>
          <button class="primary-button large" :disabled="!activeTemplate.available" @click="configuring = !configuring">Configure analysis →</button>
        </div>
      </article>

      <form v-if="configuring && activeTemplate" class="analysis-period-form" @submit.prevent="launch(activeTemplate)">
        <header><div><strong>Configure metric investigation</strong><small>Choose governed definitions, then compare equally sized periods.</small></div></header>
        <section v-if="genericTemplate" class="analysis-definition-form">
          <label><span>Metric</span><select v-model="metricName" required><option v-for="metric in metricOptions" :key="metric.name" :value="metric.name">{{ metric.label }}</option></select></label>
          <label><span>Time dimension</span><select v-model="timeDimensionName" required><option v-for="dimension in timeDimensionOptions" :key="dimension.name" :value="dimension.name">{{ dimension.label }} · month</option></select></label>
          <label><span>Component metric (optional)</span><select v-model="componentMetricName"><option value="">None</option><option v-for="metric in componentMetricOptions" :key="metric.name" :value="metric.name">{{ metric.label }}</option></select></label>
          <fieldset v-if="sliceDimensionOptions.length" class="slice-picker"><legend>Break down by up to three dimensions</legend><label v-for="dimension in sliceDimensionOptions" :key="dimension.name"><input type="checkbox" :checked="sliceDimensionNames.includes(dimension.name)" :disabled="!sliceDimensionNames.includes(dimension.name) && sliceDimensionNames.length >= 3" @change="toggleSlice(dimension.name)" />{{ dimension.label }}</label></fieldset>
        </section>
        <fieldset><legend>Current period</legend><label>From<input v-model="currentStart" type="date" required /></label><label>To<input v-model="currentEnd" type="date" required /></label></fieldset>
        <fieldset><legend>Comparison period</legend><label>From<input v-model="previousStart" type="date" required /></label><label>To<input v-model="previousEnd" type="date" required /></label></fieldset>
        <button class="primary-button large" type="submit" :disabled="!canLaunch">Run analysis</button>
      </form>

      <section v-if="studio.analysisRuns.length" class="analysis-history">
        <header><strong>Recent analyses</strong><small>Reports and evidence survive Studio restarts.</small></header>
        <button v-for="item in studio.analysisRuns.slice(0, 6)" :key="item.id" @click="studio.openAnalysisRun(item.id)">
          <span :class="['run-state', item.state]" /><div><strong>{{ item.definition_name }}</strong><small>{{ new Date(item.created_at).toLocaleString() }}</small></div>
          <span>{{ item.state.replace('_', ' ') }}</span><i>→</i>
        </button>
      </section>
    </div>

    <div v-else-if="!terminal" class="analysis-running">
      <span class="analysis-running-mark">✦</span>
      <p class="eyebrow">{{ run.state }}</p><h1>Investigating metric change</h1>
      <p>{{ completedSteps }} of {{ run.steps.length || '…' }} semantic queries completed. Each result is preserved as evidence.</p>
      <div class="analysis-progress"><i :style="{ width: `${run.steps.length ? completedSteps / run.steps.length * 100 : 8}%` }" /></div>
      <ol><li v-for="step in run.steps" :key="step.id" :class="step.state"><span>{{ step.state === 'completed' ? '✓' : step.state === 'running' ? '↻' : '·' }}</span><div><strong>{{ step.title }}</strong><small>{{ step.kind.replaceAll('_', ' ') }}</small></div></li></ol>
      <button class="cancel-button" @click="studio.cancelAnalysis">Cancel analysis</button>
    </div>

    <div v-else class="analysis-report">
      <header class="report-header">
        <div><p class="eyebrow">{{ run.definition_name }}</p><h1>{{ run.report.headline || (run.error ?? 'Analysis complete') }}</h1><p>{{ run.report.summary }}</p></div>
        <div class="report-actions"><button class="secondary-button" @click="studio.exportAnalysis('html')">Export HTML</button><button class="primary-button" @click="studio.exportAnalysis('pdf')">Export PDF</button></div>
      </header>
      <section v-if="run.report.confidence_score !== undefined" class="confidence-card">
        <div><span>Confidence</span><strong>{{ run.report.confidence_score }}%</strong><small>{{ run.report.confidence }} confidence</small></div>
        <dl><div><dt>Evidence coverage</dt><dd>{{ run.report.confidence_basis?.evidence_coverage }}%</dd></div><div><dt>Data completeness</dt><dd>{{ run.report.confidence_basis?.data_completeness }}%</dd></div><div><dt>Semantic trust</dt><dd>{{ run.report.confidence_basis?.semantic_trust ?? 100 }}%</dd></div><div><dt>Queries executed</dt><dd>{{ run.evidence.length }}</dd></div></dl>
      </section>
      <section v-if="run.charts.length" class="analysis-charts"><AnalysisChart v-for="chart in run.charts" :key="chart.id" :chart="chart" /></section>
      <section class="findings-panel">
        <header><strong>Findings</strong><small>Deterministic comparisons, not generated assertions</small></header>
        <article v-for="finding in run.findings" :key="finding.id">
          <span :class="['finding-direction', finding.direction]">{{ finding.direction === 'decreased' ? '↓' : finding.direction === 'increased' ? '↑' : '◇' }}</span>
          <div><strong>{{ finding.title }}</strong><p>{{ finding.claim }}</p><small>{{ finding.evidence_ids.length }} evidence source{{ finding.evidence_ids.length === 1 ? '' : 's' }} · {{ finding.method.replaceAll('_', ' ') }}</small></div>
          <button v-if="finding.follow_up_analysis" class="secondary-button" :disabled="studio.activity === 'analysis'" @click="studio.investigateFinding(finding.id)">Investigate →</button>
        </article>
      </section>
      <section class="evidence-panel">
        <header><strong>Evidence</strong><small>Inspect the semantic plan, bound SQL and returned data behind every finding.</small></header>
        <details v-for="item in run.evidence" :key="item.id">
          <summary><span :class="['evidence-state', item.status]">{{ item.status === 'succeeded' ? '✓' : '!' }}</span><div><strong>{{ item.title }}</strong><small>{{ item.row_count }} rows · {{ item.duration_ms.toFixed(1) }} ms</small></div><code>{{ item.step_id }}</code></summary>
          <div class="evidence-detail"><label>Semantic plan</label><pre>{{ JSON.stringify(item.semantic_plan, null, 2) }}</pre><label>Compiled SQL</label><pre>{{ item.compiled_sql }}</pre><label>Bound parameters</label><pre>{{ JSON.stringify(item.parameters, null, 2) }}</pre>
            <div class="evidence-table"><table><thead><tr><th v-for="column in item.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in item.rows.slice(0, 20)" :key="rowIndex"><td v-for="(value, columnIndex) in row" :key="columnIndex">{{ value }}</td></tr></tbody></table></div>
          </div>
        </details>
      </section>
    </div>
  </section>
</template>
