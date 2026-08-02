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
} from "../api";
import type {
  ConnectionProfile,
  ConnectionTest,
  DatabaseObject,
  HistoryEntry,
  ModelStatus,
  QueryExecution,
  QueryDocument,
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
  | "save-connection"
  | "demo"
  | "model"
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
        );
        this.activeDocument.generated_sql = generated.sql;
        this.activeDocument.edited_sql = generated.sql;
        this.activeDocument.lifecycle_state = "generated";
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
        this.activeDocument.lifecycle_state = "running";
        let job = await startExecution(this.selectedConnection, this.activeDocument.edited_sql.trim(), {
          historyId: this.generatedHistoryId || undefined,
          question: this.activeDocument.question.trim() || undefined,
          model: this.generatedHistoryId ? this.model : undefined,
          source: this.generatedHistoryId ? "ai" : "manual",
          documentId: this.activeDocument.id,
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
        await exportQuery(this.selectedConnection, this.activeDocument.edited_sql.trim(), format);
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
  },
});

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
