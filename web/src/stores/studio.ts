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
  generateSqlStream,
  deleteHistory,
  pinHistory,
  removeConnection,
  reviewWrite,
  startExecution,
  testConnection,
  updateConnection,
} from "../api";
import type {
  ConnectionProfile,
  ConnectionTest,
  DatabaseObject,
  HistoryEntry,
  ModelStatus,
  QueryExecution,
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

export const useStudioStore = defineStore("studio", {
  state: () => ({
    connections: [] as ConnectionProfile[],
    selectedConnection: "",
    tables: [] as TableSchema[],
    views: [] as DatabaseObject[],
    triggers: [] as DatabaseObject[],
    selectedTables: [] as string[],
    queryPlan: null as { columns: string[]; rows: unknown[][] } | null,
    question: "",
    sql: "select 1 as ready",
    model: initialModel,
    modelStatus: null as ModelStatus | null,
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
    busy: (state): boolean => state.activity !== null,
  },
  actions: {
    async initialise() {
      this.activity = "connections";
      this.error = "";
      try {
        this.connections = await fetchConnections();
        if (this.connections.length) {
          const requested = new URLSearchParams(window.location.search).get("connection");
          const remembered = window.localStorage.getItem("asksql-connection");
          const target = [requested, remembered, this.connections[0].name].find(
            (name) => name && this.connections.some((profile) => profile.name === name),
          );
          await this.selectConnection(target ?? this.connections[0].name);
        }
        await this.loadHistory();
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
    },
    async selectConnection(name: string) {
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
        this.selectedTables = details.tables.map((table) => table.name);
        const draft = window.localStorage.getItem(`asksql-draft:${name}`);
        if (draft) {
          try {
            const restored = JSON.parse(draft) as { question?: string; sql?: string };
            this.question = restored.question ?? "";
            this.sql = restored.sql ?? "select 1 as ready";
          } catch {
            window.localStorage.removeItem(`asksql-draft:${name}`);
          }
        }
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activity = null;
      }
    },
    async generate() {
      if (!this.selectedConnection || !this.question.trim()) return;
      this.activity = "generate";
      this.error = "";
      this.execution = null;
      try {
        const generated = await generateSqlStream(
          this.selectedConnection,
          this.question.trim(),
          this.model,
          (event) => { this.generationStatus = String(event.event ?? ""); },
          this.selectedTables.length === this.tables.length ? undefined : this.selectedTables,
        );
        this.sql = generated.sql;
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
      if (!this.selectedConnection || !this.sql.trim()) return;
      this.activity = "execute";
      this.error = "";
      try {
        let job = await startExecution(this.selectedConnection, this.sql.trim(), {
          historyId: this.generatedHistoryId || undefined,
          question: this.question.trim() || undefined,
          model: this.generatedHistoryId ? this.model : undefined,
          source: this.generatedHistoryId ? "ai" : "manual",
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
      if (!this.selectedConnection || !this.sql.trim()) return;
      this.error = "";
      try {
        await exportQuery(this.selectedConnection, this.sql.trim(), format);
      } catch (error) {
        this.error = message(error);
      }
    },
    async prepareWrite() {
      if (!this.selectedConnection || !this.sql.trim()) return;
      this.error = "";
      try {
        this.writeReview = await reviewWrite(this.selectedConnection, this.sql.trim());
      } catch (error) {
        this.error = message(error);
      }
    },
    async commitWrite() {
      if (!this.writeReview || !this.selectedConnection) return;
      this.activity = "execute";
      this.error = "";
      try {
        let job = await commitWrite(this.selectedConnection, this.sql.trim(), this.writeReview.token);
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
    },
    previewTable(table: TableSchema) {
      this.sql = `select *\nfrom "${table.name.replaceAll('"', '""')}"\nlimit 50`;
      this.execution = null;
      this.activeHistoryId = "";
      this.generatedHistoryId = "";
    },
    persistDraft() {
      if (!this.selectedConnection) return;
      window.localStorage.setItem(
        `asksql-draft:${this.selectedConnection}`,
        JSON.stringify({ question: this.question, sql: this.sql }),
      );
    },
    toggleContextTable(name: string) {
      this.selectedTables = this.selectedTables.includes(name)
        ? this.selectedTables.filter((item) => item !== name)
        : [...this.selectedTables, name];
    },
    async explain() {
      if (!this.selectedConnection || !this.sql.trim()) return;
      this.error = "";
      try {
        this.queryPlan = await explainQuery(this.selectedConnection, this.sql.trim());
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
      this.question = entry.question ?? "";
      this.sql = entry.sql;
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
  },
});

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
