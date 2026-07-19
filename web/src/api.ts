import type { ConnectionProfile, ConnectionTest, ModelStatus, QueryExecution, TableSchema } from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed (${response.status})`);
  }
  return payload as T;
}

export async function fetchConnections(): Promise<ConnectionProfile[]> {
  const payload = await request<{ connections: ConnectionProfile[] }>("/api/connections");
  return payload.connections;
}

export function testConnection(url: string): Promise<ConnectionTest> {
  return request<ConnectionTest>("/api/connections/test", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function addConnection(name: string, url: string): Promise<ConnectionProfile> {
  return request<ConnectionProfile>("/api/connections", {
    method: "POST",
    body: JSON.stringify({ name, url }),
  });
}

export function updateConnection(originalName: string, name: string, url: string): Promise<ConnectionProfile> {
  return request<ConnectionProfile>(`/api/connections/${encodeURIComponent(originalName)}`, {
    method: "PUT",
    body: JSON.stringify({ name, url }),
  });
}

export function removeConnection(name: string): Promise<void> {
  return request<void>(`/api/connections/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export function addDemoConnection(): Promise<ConnectionProfile> {
  return request<ConnectionProfile>("/api/connections/demo", { method: "POST" });
}

export function checkModel(model: string): Promise<ModelStatus> {
  return request<ModelStatus>("/api/models/check", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export async function fetchSchema(connection: string): Promise<TableSchema[]> {
  const payload = await request<{ tables: TableSchema[] }>(
    `/api/connections/${encodeURIComponent(connection)}/schema`,
  );
  return payload.tables;
}

export async function generateSql(connection: string, question: string, model: string): Promise<string> {
  const payload = await request<{ sql: string }>("/api/query/generate", {
    method: "POST",
    body: JSON.stringify({ connection, question, model }),
  });
  return payload.sql;
}

export function executeSql(connection: string, sql: string): Promise<QueryExecution> {
  return request<QueryExecution>("/api/query/execute", {
    method: "POST",
    body: JSON.stringify({ connection, sql }),
  });
}
