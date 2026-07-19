import type { ConnectionProfile, QueryExecution, TableSchema } from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed (${response.status})`);
  }
  return payload as T;
}

export async function fetchConnections(): Promise<ConnectionProfile[]> {
  const payload = await request<{ connections: ConnectionProfile[] }>("/api/connections");
  return payload.connections;
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
