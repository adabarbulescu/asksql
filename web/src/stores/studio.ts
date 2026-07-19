import { defineStore } from "pinia";

import {
  addConnection,
  addDemoConnection,
  checkModel,
  executeSql,
  fetchConnections,
  fetchSchema,
  generateSql,
  removeConnection,
  testConnection,
  updateConnection,
} from "../api";
import type { ConnectionProfile, ConnectionTest, ModelStatus, QueryExecution, TableSchema } from "../types";

type Activity = "connections" | "schema" | "generate" | "execute" | "save-connection" | "demo" | "model" | null;

const initialModel =
  new URLSearchParams(window.location.search).get("model") ??
  window.localStorage.getItem("asksql-model") ??
  "ollama:qwen2.5-coder:7b";

export const useStudioStore = defineStore("studio", {
  state: () => ({
    connections: [] as ConnectionProfile[],
    selectedConnection: "",
    tables: [] as TableSchema[],
    question: "",
    sql: "select 1 as ready",
    model: initialModel,
    modelStatus: null as ModelStatus | null,
    execution: null as QueryExecution | null,
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
          await this.selectConnection(this.connections[0].name);
        }
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
      this.tables = [];
      this.execution = null;
      this.activity = "schema";
      this.error = "";
      try {
        this.tables = await fetchSchema(name);
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
        this.sql = await generateSql(this.selectedConnection, this.question.trim(), this.model);
      } catch (error) {
        this.error = message(error);
      } finally {
        this.activity = null;
      }
    },
    async execute() {
      if (!this.selectedConnection || !this.sql.trim()) return;
      this.activity = "execute";
      this.error = "";
      try {
        this.execution = await executeSql(this.selectedConnection, this.sql.trim());
        if (this.execution.status !== "succeeded") {
          this.error = this.execution.error ?? "Query failed";
        }
      } catch (error) {
        this.error = message(error);
      } finally {
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
    },
  },
});

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}
