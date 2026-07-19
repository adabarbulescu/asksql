import { defineStore } from "pinia";

import { executeSql, fetchConnections, fetchSchema, generateSql } from "../api";
import type { ConnectionProfile, QueryExecution, TableSchema } from "../types";

type Activity = "connections" | "schema" | "generate" | "execute" | null;

export const useStudioStore = defineStore("studio", {
  state: () => ({
    connections: [] as ConnectionProfile[],
    selectedConnection: "",
    tables: [] as TableSchema[],
    question: "",
    sql: "select 1 as ready",
    model: new URLSearchParams(window.location.search).get("model") ?? "ollama:qwen2.5-coder:7b",
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
    previewTable(table: TableSchema) {
      this.sql = `select *\nfrom "${table.name.replaceAll('"', '""')}"\nlimit 50`;
      this.execution = null;
    },
  },
});

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}
