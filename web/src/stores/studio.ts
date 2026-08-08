import { defineStore } from "pinia";

import {
  addConnection,
  addDemoConnection,
  checkModel,
  commitWrite,
  cancelExecutionJob,
  exportQuery,
  explainQuery,
  fetchExecutionJob,
  fetchConnections,
  fetchHistory,
  fetchSchema,
  fetchSetup,
  generateSqlStream,
  deleteHistory,
  pinHistory,
  removeConnection,
  reviewWrite,
  startExecution,
  testConnection,
  updateConnection,
  createQueryDocument,
  deleteQueryDocument,
  fetchWorkspace,
  setWorkspaceActive,
  updateQueryDocument,
  createSavedQuery,
  deleteSavedQuery,
  duplicateSavedQuery,
  fetchSavedQueries,
  updateSavedQuery,
  createSemanticModel,
  checkSemanticReadiness,
  deleteSemanticModel,
  fetchSemanticModels,
  proposeSemanticModel,
  updateSemanticModel,
  cancelAnalysisRun,
  createAnalysisFromTemplate,
  exportAnalysisReport,
  fetchAnalysisDefinitions,
  fetchAnalysisRun,
  fetchAnalysisRuns,
  fetchAnalysisTemplates,
  followUpAnalysis,
  startAnalysisRun,
} from "../api";
import type {
  AnalysisDefinition,
  AnalysisRun,
  AnalysisTemplate,
  AnalysisTemplateSelection,
  ConnectionProfile,
  ConnectionTest,
  DatabaseObject,
  HistoryEntry,
  ModelStatus,
  QueryExecution,
  QueryDocument,
  SavedQuery,
  SavedQueryParameter,
  SemanticModel,
  SemanticModelInput,
  SemanticDraft,
  SemanticReadiness,
  SemanticTraceItem,
  SetupStatus,
  TableSchema,
  WriteReview,
} from "../types";

type Activity =
  | "connections"
  | "schema"
  | "generate"
  | "execute"
  | "history"
  | "library"
  | "save-connection"
  | "demo"
  | "model"
  | "semantic"
  | "analysis"
  | null;

const initialModel =
  new URLSearchParams(window.location.search).get("model") ??
  window.localStorage.getItem("asksql-model") ??
  "ollama:qwen2.5-coder:7b";

const persistTimers = new Map<string, number>();

export const useStudioStore = defineStore("studio", {
  state: () => ({
    connections: [] as ConnectionProfile[],
    selectedConnection: "",
    tables: [] as TableSchema[],
    views: [] as DatabaseObject[],
    triggers: [] as DatabaseObject[],
    selectedTables: [] as string[],
    documents: [] as QueryDocument[],
    activeDocumentId: "",
    queryPlan: null as { columns: string[]; rows: unknown[][] } | null,
    model: initialModel,
    modelStatus: null as ModelStatus | null,
    setupStatus: null as SetupStatus | null,
    execution: null as QueryExecution | null,
    history: [] as HistoryEntry[],
    savedQueries: [] as SavedQuery[],
    semanticModels: [] as SemanticModel[],
    semanticDraft: null as SemanticDraft | null,
    semanticReadiness: null as SemanticReadiness | null,
    selectedSemanticModelId: "",
    generationMode: "" as "" | "semantic" | "freeform",
    semanticTrace: [] as SemanticTraceItem[],
    analysisTemplates: [] as AnalysisTemplate[],
    analysisDefinitions: [] as AnalysisDefinition[],
    analysisRuns: [] as AnalysisRun[],
    activeAnalysisRun: null as AnalysisRun | null,
    savedQueryFolders: [] as string[],
    savedQueryTags: [] as string[],
    librarySearch: "",
    libraryFolder: undefined as string | undefined,
    libraryTag: undefined as string | undefined,
    libraryFavoritesOnly: false,
    historySearch: "",
    activeHistoryId: "",
    generatedHistoryId: "",
    activeJobId: "",
    generationStatus: "",
    writeReview: null as WriteReview | null,
    activity: null as Activity,
    error: "",
  }),
  getters: {
    selectedProfile(state): ConnectionProfile | undefined {
      return state.connections.find((item) => item.name === state.selectedConnection);
    },
    activeDocument(state): QueryDocument | undefined {
      return state.documents.find((document) => document.id === state.activeDocumentId);
    },
    busy: (state): boolean => state.activity !== null,
  },
  actions: {
    async initialise() {
      this.activity = "connections";
      this.error = "";
      try {
        this.connections = await fetchConnections();
        if (this.connections.length) {
          const workspace = await fetchWorkspace();
          this.documents = workspace.documents;
          this.activeDocumentId = workspace.activeDocumentId ?? workspace.documents[0]?.id ?? "";
          const requested = new URLSearchParams(window.location.search).get("connection");
          const target = [requested, this.activeDocument?.connection, workspace.activeConnection, this.connections[0].name].find(
            (name) => name && this.connections.some((profile) => profile.name === name),
          );
          await this.selectConnection(target ?? this.connections[0].name, false);
          if (!this.documents.length) await this.newDocument();
        }
        await this.loadHistory();
        await this.loadSavedQueries();
        await this.loadSemanticModels();
        await this.loadSetup();
        const historyId = new URLSearchParams(window.location.search).get("history");
        const entry = this.history.find((item) => item.id === historyId);
        if (entry) await this.restoreHistory(entry);
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activity = null;
      }
    },
    async reloadConnections(selectedName?: string) {
      this.connections = await fetchConnections();
      const target = selectedName || this.selectedConnection || this.connections[0]?.name;
      if (target && this.connections.some((item) => item.name === target)) {
        await this.selectConnection(target);
      } else {
        this.selectedConnection = "";
        this.tables = [];
        this.execution = null;
      }
      await this.loadSetup();
    },
    async selectConnection(name: string, updateDocument = true) {
      if (name !== this.selectedConnection) {
        this.semanticDraft = null;
        this.semanticReadiness = null;
      }
      this.selectedConnection = name;
      window.localStorage.setItem("asksql-connection", name);
      this.tables = [];
      this.execution = null;
      this.activity = "schema";
      this.error = "";
      try {
        const details = await fetchSchema(name);
        this.tables = details.tables;
        this.views = details.views;
        this.triggers = details.triggers;
        await this.loadSemanticModels(name);
        const available = new Set(details.tables.map((table) => table.name));
        const saved = this.activeDocument?.selected_tables ?? [];
        this.selectedTables = saved.length ? saved.filter((table) => available.has(table)) : [...available];
        if (updateDocument && this.activeDocument) {
          const updated = await updateQueryDocument(this.activeDocument.id, {
            connection: name,
            selected_tables: this.selectedTables,
          });
          this.replaceDocument(updated);
          await setWorkspaceActive(name, updated.id);
        }
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activity = null;
      }
    },
    async generate() {
      if (!this.selectedConnection || !this.activeDocument?.question.trim()) return;
      this.cancelPendingPersist(this.activeDocument.id);
      this.activity = "generate";
      this.error = "";
      this.execution = null;
      try {
        const generated = await generateSqlStream(
          this.selectedConnection,
          this.activeDocument.question.trim(),
          this.model,
          (event) => { this.generationStatus = String(event.event ?? ""); },
          this.selectedTables.length === this.tables.length ? undefined : this.selectedTables,
          this.activeDocument.id,
          this.selectedSemanticModelId || undefined,
        );
        this.activeDocument.generated_sql = generated.sql;
        this.activeDocument.edited_sql = generated.sql;
        this.activeDocument.lifecycle_state = "generated";
        this.activeDocument.semantic_model_id = generated.modelId;
        this.activeDocument.semantic_plan = generated.plan;
        this.generationMode = generated.generationMode;
        this.semanticTrace = generated.trace;
        this.activeHistoryId = generated.historyId;
        this.generatedHistoryId = generated.historyId;
        await this.loadHistory();
      } catch (error) {
        this.error = message(error);
      } finally {
        this.generationStatus = "";
        this.activity = null;
      }
    },
    async execute() {
      if (!this.selectedConnection || !this.activeDocument?.edited_sql.trim()) return;
      this.cancelPendingPersist(this.activeDocument.id);
      this.activity = "execute";
      this.error = "";
      try {
        this.validateActiveParameters();
        this.activeDocument.lifecycle_state = "running";
        let job = await startExecution(this.selectedConnection, this.activeDocument.edited_sql.trim(), {
          historyId: this.generatedHistoryId || undefined,
          question: this.activeDocument.question.trim() || undefined,
          model: this.generatedHistoryId ? this.model : undefined,
          source: this.generatedHistoryId ? "ai" : "manual",
          documentId: this.activeDocument.id,
          savedQueryId: this.activeDocument.saved_query_id ?? undefined,
          parameterValues: this.activeDocument.parameter_values,
          semanticModelId: this.activeDocument.semantic_model_id ?? undefined,
          semanticPlan: this.activeDocument.semantic_plan,
        });
        this.activeJobId = job.jobId;
        this.activeHistoryId = job.historyId;
        this.generatedHistoryId = "";
        while (job.state !== "completed") {
          await delay(120);
          job = await fetchExecutionJob(job.jobId);
        }
        this.execution = job.execution ?? null;
        if (!this.execution) throw new Error("Execution completed without a result");
        if (this.execution.status !== "succeeded") {
          this.error = this.execution.error ?? "Query failed";
        }
        const snapshot = await fetchWorkspace();
        this.documents = snapshot.documents;
        await this.loadHistory();
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activeJobId = "";
        this.activity = null;
      }
    },
    async cancelExecution() {
      if (!this.activeJobId) return;
      try {
        await cancelExecutionJob(this.activeJobId);
      } catch (error) {
        this.error = message(error);
      }
    },
    async exportResults(format: "csv" | "json" | "markdown") {
      if (!this.selectedConnection || !this.activeDocument?.edited_sql.trim()) return;
      this.error = "";
      try {
        this.validateActiveParameters();
        await exportQuery(this.selectedConnection, this.activeDocument.edited_sql.trim(), format,
          this.activeDocument.saved_query_id ?? undefined, this.activeDocument.parameter_values,
          this.activeDocument.semantic_model_id ?? undefined, this.activeDocument.semantic_plan);
      } catch (error) {
        this.error = message(error);
      }
    },
    async prepareWrite() {
      if (!this.selectedConnection || !this.activeDocument?.edited_sql.trim()) return;
      this.error = "";
      try {
        this.writeReview = await reviewWrite(this.selectedConnection, this.activeDocument.edited_sql.trim());
      } catch (error) {
        this.error = message(error);
      }
    },
    async commitWrite() {
      if (!this.writeReview || !this.selectedConnection) return;
      this.activity = "execute";
      this.error = "";
      try {
        let job = await commitWrite(this.selectedConnection, this.activeDocument?.edited_sql.trim() ?? "", this.writeReview.token);
        this.writeReview = null;
        this.activeJobId = job.jobId;
        this.activeHistoryId = job.historyId;
        while (job.state !== "completed") {
          await delay(120);
          job = await fetchExecutionJob(job.jobId);
        }
        this.execution = job.execution ?? null;
        if (!this.execution) throw new Error("Write completed without a result");
        if (this.execution.status !== "succeeded") this.error = this.execution.error ?? "Write failed";
        await this.loadHistory();
        this.tables = (await fetchSchema(this.selectedConnection)).tables;
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activeJobId = "";
        this.activity = null;
      }
    },
    async testDatabase(url: string): Promise<ConnectionTest> {
      this.error = "";
      try {
        return await testConnection(url);
      } catch (error) {
        this.error = message(error);
        throw error;
      }
    },
    async saveConnection(name: string, url: string, originalName?: string) {
      this.activity = "save-connection";
      this.error = "";
      try {
        const profile = originalName
          ? await updateConnection(originalName, name, url)
          : await addConnection(name, url);
        await this.reloadConnections(profile.name);
        return profile;
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    async deleteConnection(name: string) {
      this.activity = "save-connection";
      this.error = "";
      try {
        await removeConnection(name);
        this.selectedConnection = "";
        await this.reloadConnections();
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    async useDemo() {
      this.activity = "demo";
      this.error = "";
      try {
        const profile = await addDemoConnection();
        await this.reloadConnections(profile.name);
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    async verifyModel(): Promise<ModelStatus> {
      this.activity = "model";
      this.error = "";
      this.modelStatus = null;
      try {
        this.modelStatus = await checkModel(this.model);
        this.setupStatus = await fetchSetup(this.model, true);
        return this.modelStatus;
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    setModel(model: string) {
      this.model = model;
      this.modelStatus = null;
      window.localStorage.setItem("asksql-model", model);
      void this.loadSetup();
    },
    async loadSetup(checkModel = false) {
      this.setupStatus = await fetchSetup(this.model, checkModel);
    },
    previewTable(table: TableSchema) {
      if (!this.activeDocument) return;
      this.activeDocument.edited_sql = `select *\nfrom "${table.name.replaceAll('"', '""')}"\nlimit 50`;
      this.activeDocument.lifecycle_state = "draft";
      this.execution = null;
      this.activeHistoryId = "";
      this.generatedHistoryId = "";
    },
    persistDraft() {
      if (!this.activeDocument) return;
      const identifier = this.activeDocument.id;
      const payload = {
        question: this.activeDocument.question,
        edited_sql: this.activeDocument.edited_sql,
        selected_tables: [...this.selectedTables],
        lifecycle_state: this.activeDocument.lifecycle_state,
        saved_query_id: this.activeDocument.saved_query_id,
        parameter_values: this.activeDocument.parameter_values,
        semantic_model_id: this.activeDocument.semantic_model_id,
        semantic_plan: this.activeDocument.semantic_plan,
      };
      this.cancelPendingPersist(identifier);
      persistTimers.set(identifier, window.setTimeout(() => {
        persistTimers.delete(identifier);
        void updateQueryDocument(identifier, payload).catch((error) => { this.error = message(error); });
      }, 250));
    },
    toggleContextTable(name: string) {
      this.selectedTables = this.selectedTables.includes(name)
        ? this.selectedTables.filter((item) => item !== name)
        : [...this.selectedTables, name];
      if (this.activeDocument) this.activeDocument.selected_tables = [...this.selectedTables];
    },
    async explain() {
      if (!this.selectedConnection || !this.activeDocument?.edited_sql.trim()) return;
      this.error = "";
      try {
        this.queryPlan = await explainQuery(this.selectedConnection, this.activeDocument.edited_sql.trim());
      } catch (error) {
        this.error = message(error);
      }
    },
    async loadHistory(search?: string) {
      const previous = this.activity;
      if (!previous) this.activity = "history";
      try {
        const value = search ?? this.historySearch;
        this.history = await fetchHistory(undefined, value.trim() || undefined);
      } finally {
        if (!previous) this.activity = null;
      }
    },
    async restoreHistory(entry: HistoryEntry) {
      if (this.connections.some((profile) => profile.name === entry.connection)) {
        await this.selectConnection(entry.connection);
      }
      const document = await createQueryDocument(entry.connection, entry.question || "Saved query");
      document.question = entry.question ?? "";
      document.edited_sql = entry.sql;
      document.lifecycle_state = entry.status === "succeeded" ? "completed" : "draft";
      this.documents.push(document);
      this.activeDocumentId = document.id;
      await this.persistDocument();
      this.activeHistoryId = entry.id;
      this.generatedHistoryId = "";
      this.execution = null;
      const url = new URL(window.location.href);
      url.searchParams.set("connection", entry.connection);
      url.searchParams.set("history", entry.id);
      window.history.replaceState(null, "", url);
    },
    async toggleHistoryPin(entry: HistoryEntry) {
      await pinHistory(entry.id, !entry.pinned);
      await this.loadHistory();
    },
    async removeHistory(entry: HistoryEntry) {
      await deleteHistory(entry.id);
      if (this.activeHistoryId === entry.id) this.activeHistoryId = "";
      await this.loadHistory();
    },
    async loadSavedQueries() {
      const library = await fetchSavedQueries({
        search: this.librarySearch.trim() || undefined,
        folder: this.libraryFolder,
        tag: this.libraryTag,
        favorite: this.libraryFavoritesOnly ? true : undefined,
      });
      this.savedQueries = library.savedQueries;
      this.savedQueryFolders = library.folders;
      this.savedQueryTags = library.tags;
    },
    async saveActiveQuery(details: { name: string; description: string; folder?: string; tags: string[]; parameters: SavedQueryParameter[] }, saveAs = false) {
      if (!this.activeDocument) return;
      this.cancelPendingPersist(this.activeDocument.id);
      await this.persistDocument();
      const existing = saveAs
        ? undefined
        : this.savedQueries.find((item) => item.id === this.activeDocument?.saved_query_id)
          ?? this.savedQueries.find((item) => item.source_document_id === this.activeDocument?.id);
      const payload = {
        name: details.name,
        description: details.description,
        connection_hint: this.activeDocument.connection,
        natural_language_question: this.activeDocument.question,
        sql: this.activeDocument.edited_sql,
        schema_context: [...this.selectedTables],
        tags: details.tags,
        folder: details.folder || null,
        favorite: existing?.favorite ?? false,
        source_document_id: this.activeDocument.id,
        parameters: details.parameters,
      };
      const saved = existing ? await updateSavedQuery(existing.id, payload) : await createSavedQuery(payload);
      this.activeDocument.saved_query_id = saved.id;
      await this.persistDocument();
      await this.loadSavedQueries();
    },
    async openSavedQuery(item: SavedQuery) {
      const connection = this.connections.some((profile) => profile.name === item.connection_hint)
        ? item.connection_hint
        : this.selectedConnection;
      if (!connection) return;
      const defaults = Object.fromEntries(item.parameters.filter((parameter) => !parameter.sensitive && parameter.default_value != null)
        .map((parameter) => [parameter.name, parameter.default_value]));
      const document = await createQueryDocument(connection, item.name, item.id, defaults);
      document.question = item.natural_language_question;
      document.edited_sql = item.sql;
      document.generated_sql = item.sql;
      document.selected_tables = [...item.schema_context];
      document.lifecycle_state = "draft";
      document.saved_query_id = item.id;
      document.parameter_values = defaults;
      this.documents.push(document);
      this.activeDocumentId = document.id;
      await this.persistDocument();
      await updateSavedQuery(item.id, { source_document_id: document.id });
      await this.activateDocument(document.id);
      await this.loadSavedQueries();
    },
    async duplicateSavedQueryItem(item: SavedQuery) {
      await duplicateSavedQuery(item.id);
      await this.loadSavedQueries();
    },
    async toggleSavedQueryFavorite(item: SavedQuery) {
      await updateSavedQuery(item.id, { favorite: !item.favorite });
      await this.loadSavedQueries();
    },
    async removeSavedQueryItem(item: SavedQuery) {
      await deleteSavedQuery(item.id);
      await this.loadSavedQueries();
    },
    async newDocument() {
      if (!this.selectedConnection) return;
      const document = await createQueryDocument(this.selectedConnection, `Query ${this.documents.length + 1}`);
      this.documents.push(document);
      await this.activateDocument(document.id);
    },
    async activateDocument(identifier: string) {
      const document = this.documents.find((item) => item.id === identifier);
      if (!document) return;
      this.activeDocumentId = identifier;
      this.execution = null;
      this.error = document.error ?? "";
      await this.selectConnection(document.connection, false);
      this.selectedTables = document.selected_tables.length
        ? [...document.selected_tables]
        : this.tables.map((table) => table.name);
      await setWorkspaceActive(document.connection, identifier);
    },
    async closeDocument(identifier: string) {
      if (this.documents.length === 1) return;
      const index = this.documents.findIndex((item) => item.id === identifier);
      await deleteQueryDocument(identifier);
      this.documents.splice(index, 1);
      if (this.activeDocumentId === identifier) {
        await this.activateDocument(this.documents[Math.max(0, index - 1)].id);
      }
    },
    async renameDocument(identifier: string, title: string) {
      const updated = await updateQueryDocument(identifier, { title });
      this.replaceDocument(updated);
    },
    async persistDocument() {
      if (!this.activeDocument) return;
      const updated = await updateQueryDocument(this.activeDocument.id, {
        question: this.activeDocument.question,
        edited_sql: this.activeDocument.edited_sql,
        selected_tables: this.selectedTables,
        lifecycle_state: this.activeDocument.lifecycle_state,
        saved_query_id: this.activeDocument.saved_query_id,
        parameter_values: this.activeDocument.parameter_values,
        semantic_model_id: this.activeDocument.semantic_model_id,
        semantic_plan: this.activeDocument.semantic_plan,
      });
      this.replaceDocument(updated);
    },
    replaceDocument(document: QueryDocument) {
      const index = this.documents.findIndex((item) => item.id === document.id);
      if (index >= 0) this.documents[index] = document;
    },
    cancelPendingPersist(identifier: string) {
      const timer = persistTimers.get(identifier);
      if (timer !== undefined) window.clearTimeout(timer);
      persistTimers.delete(identifier);
    },
    activeSavedQuery(): SavedQuery | undefined {
      return this.savedQueries.find((item) => item.id === this.activeDocument?.saved_query_id);
    },
    validateActiveParameters() {
      const saved = this.activeSavedQuery();
      if (!saved || !this.activeDocument) return;
      for (const parameter of saved.parameters) {
        const value = this.activeDocument.parameter_values[parameter.name] ?? parameter.default_value;
        if (parameter.required && (value === undefined || value === null || value === "")) {
          throw new Error(`${parameter.name} is required`);
        }
        if (value === undefined || value === null || value === "") continue;
        if (parameter.data_type === "integer" && !/^-?\d+$/.test(String(value))) throw new Error(`${parameter.name} must be integer`);
        if (parameter.data_type === "decimal" && !Number.isFinite(Number(value))) throw new Error(`${parameter.name} must be decimal`);
        if (parameter.data_type === "boolean" && ![true, false, "true", "false", "1", "0"].includes(value as never)) {
          throw new Error(`${parameter.name} must be boolean`);
        }
        if (parameter.data_type === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(String(value))) throw new Error(`${parameter.name} must be date`);
        if (parameter.data_type === "datetime" && Number.isNaN(Date.parse(String(value)))) throw new Error(`${parameter.name} must be datetime`);
      }
    },
    async loadSemanticModels(connection?: string) {
      const target = connection ?? this.selectedConnection;
      this.semanticModels = target ? await fetchSemanticModels(target) : [];
      const documentModel = this.activeDocument?.semantic_model_id;
      this.selectedSemanticModelId = this.semanticModels.some((item) => item.id === documentModel)
        ? documentModel ?? ""
        : this.semanticModels[0]?.id ?? "";
      await this.loadAnalysisLibrary();
    },
    async proposeBusinessModel() {
      if (!this.selectedConnection) return null;
      this.activity = "semantic";
      this.error = "";
      try {
        this.semanticDraft = await proposeSemanticModel(this.selectedConnection);
        this.semanticReadiness = await checkSemanticReadiness(this.semanticDraft.model);
        return this.semanticDraft;
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    async checkBusinessModel(model: SemanticModelInput) {
      this.activity = "semantic";
      this.error = "";
      try {
        this.semanticReadiness = await checkSemanticReadiness(model);
        return this.semanticReadiness;
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    async saveSemanticModel(model: SemanticModelInput, identifier?: string) {
      this.activity = "semantic";
      this.error = "";
      try {
        const saved = identifier ? await updateSemanticModel(identifier, model) : await createSemanticModel(model);
        await this.loadSemanticModels(saved.connection_hint);
        this.selectedSemanticModelId = saved.id;
        await this.loadAnalysisLibrary();
        this.semanticDraft = null;
        this.semanticReadiness = await checkSemanticReadiness(model);
        return saved;
      } catch (error) {
        this.error = message(error);
        throw error;
      } finally {
        this.activity = null;
      }
    },
    async removeSemanticModel(identifier: string) {
      await deleteSemanticModel(identifier);
      if (this.selectedSemanticModelId === identifier) this.selectedSemanticModelId = "";
      this.semanticReadiness = null;
      await this.loadSemanticModels();
    },
    async selectSemanticModel(identifier: string) {
      this.selectedSemanticModelId = identifier;
      this.activeAnalysisRun = null;
      this.semanticReadiness = null;
      await this.loadAnalysisLibrary();
    },
    async loadAnalysisLibrary() {
      const allRuns = await fetchAnalysisRuns();
      this.analysisRuns = this.selectedSemanticModelId
        ? allRuns.filter((item) => item.semantic_model_id === this.selectedSemanticModelId)
        : [];
      if (this.selectedSemanticModelId) {
        [this.analysisTemplates, this.analysisDefinitions] = await Promise.all([
          fetchAnalysisTemplates(this.selectedSemanticModelId),
          fetchAnalysisDefinitions(this.selectedSemanticModelId),
        ]);
      } else {
        this.analysisTemplates = [];
        this.analysisDefinitions = [];
      }
      if (!this.activeAnalysisRun || this.activeAnalysisRun.semantic_model_id !== this.selectedSemanticModelId) {
        this.activeAnalysisRun = this.analysisRuns[0] ?? null;
      }
    },
    async runAnalysis(
      template: AnalysisTemplate,
      inputValues: Record<string, unknown>,
      selection: AnalysisTemplateSelection = {},
    ) {
      if (!this.selectedSemanticModelId || !template.available) return;
      this.activity = "analysis";
      this.error = "";
      try {
        let definition = this.analysisDefinitions.find((item) =>
          item.template === template.id
          && item.semantic_model_id === this.selectedSemanticModelId
          && definitionMatches(item, selection));
        if (!definition) {
          definition = await createAnalysisFromTemplate(this.selectedSemanticModelId, template.id, selection);
          this.analysisDefinitions.unshift(definition);
        }
        this.activeAnalysisRun = await startAnalysisRun(definition.id, inputValues);
        await this.pollAnalysis(this.activeAnalysisRun.id);
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activity = null;
      }
    },
    async pollAnalysis(identifier: string) {
      let run = await fetchAnalysisRun(identifier);
      while (["planning", "running"].includes(run.state)) {
        this.activeAnalysisRun = run;
        await delay(180);
        run = await fetchAnalysisRun(identifier);
      }
      this.activeAnalysisRun = run;
      await this.loadAnalysisLibrary();
    },
    async openAnalysisRun(identifier: string) {
      this.activeAnalysisRun = await fetchAnalysisRun(identifier);
      if (["planning", "running"].includes(this.activeAnalysisRun.state)) {
        void this.pollAnalysis(identifier);
      }
    },
    async cancelAnalysis() {
      if (!this.activeAnalysisRun || !["planning", "running"].includes(this.activeAnalysisRun.state)) return;
      await cancelAnalysisRun(this.activeAnalysisRun.id);
    },
    async investigateFinding(findingId: string) {
      if (!this.activeAnalysisRun) return;
      this.activity = "analysis";
      this.error = "";
      try {
        this.activeAnalysisRun = await followUpAnalysis(this.activeAnalysisRun.id, findingId);
        await this.pollAnalysis(this.activeAnalysisRun.id);
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activity = null;
      }
    },
    async exportAnalysis(format: "pdf" | "html") {
      if (!this.activeAnalysisRun) return;
      try {
        await exportAnalysisReport(this.activeAnalysisRun.id, format);
      } catch (error) {
        this.error = message(error);
      }
    },
  },
});

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function definitionMatches(definition: AnalysisDefinition, selection: AnalysisTemplateSelection): boolean {
  if (!Object.keys(selection).length) return true;
  const comparison = definition.steps.find((step) => step.type === "period_comparison");
  const trend = definition.steps.find((step) => step.type === "trend");
  const decomposition = definition.steps.find((step) => step.type === "metric_decomposition");
  const slices = definition.steps
    .filter((step) => step.type === "dimensional_contribution")
    .map((step) => String(step.dimension));
  const components = Array.isArray(decomposition?.components)
    ? decomposition.components.map(String)
    : [];
  return (!selection.metric_name || comparison?.metric === selection.metric_name)
    && (!selection.time_dimension_name || trend?.dimension === selection.time_dimension_name)
    && (!selection.component_metric_name || components.includes(selection.component_metric_name))
    && (!selection.slice_dimension_names
      || selection.slice_dimension_names.every((dimension) => slices.includes(dimension)));
}
