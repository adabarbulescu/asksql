import type {
  ConnectionProfile,
  ConnectionTest,
  ExecutionJob,
  HistoryEntry,
  ModelStatus,
  QueryExecution,
  SchemaDetails,
  WriteReview,
} from "./types";

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

export function saveOpenAIKey(apiKey: string): Promise<void> {
  return request<void>("/api/settings/openai", {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function fetchSchema(connection: string): Promise<SchemaDetails> {
  return request<SchemaDetails>(`/api/connections/${encodeURIComponent(connection)}/schema/details`);
}

export function generateSql(
  connection: string,
  question: string,
  model: string,
): Promise<{ sql: string; historyId: string }> {
  return request<{ sql: string; historyId: string }>("/api/query/generate", {
    method: "POST",
    body: JSON.stringify({ connection, question, model }),
  });
}

export function executeSql(
  connection: string,
  sql: string,
  metadata: { historyId?: string; question?: string; model?: string; source?: "ai" | "manual" } = {},
): Promise<QueryExecution & { historyId: string }> {
  return request<QueryExecution & { historyId: string }>("/api/query/execute", {
    method: "POST",
    body: JSON.stringify({
      connection,
      sql,
      history_id: metadata.historyId,
      question: metadata.question,
      model: metadata.model,
      source: metadata.source ?? "manual",
    }),
  });
}

export async function generateSqlStream(
  connection: string,
  question: string,
  model: string,
  onEvent?: (event: Record<string, unknown>) => void,
  tables?: string[],
): Promise<{ sql: string; historyId: string }> {
  const response = await fetch("/api/query/generate-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connection, question, model, tables }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`SQL generation failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let completed: { sql: string; historyId: string } | undefined;
  while (true) {
    const { value, done } = await reader.read();
    buffered += decoder.decode(value, { stream: !done });
    const lines = buffered.split("\n");
    buffered = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as Record<string, unknown>;
      onEvent?.(event);
      if (event.event === "error") throw new Error(String(event.detail ?? "SQL generation failed"));
      if (event.event === "completed") {
        completed = { sql: String(event.sql), historyId: String(event.historyId) };
      }
    }
    if (done) break;
  }
  if (!completed) throw new Error("SQL generation ended without a result");
  return completed;
}

export function startExecution(
  connection: string,
  sql: string,
  metadata: { historyId?: string; question?: string; model?: string; source?: "ai" | "manual" } = {},
): Promise<ExecutionJob> {
  return request<ExecutionJob>("/api/query/jobs", {
    method: "POST",
    body: JSON.stringify({
      connection,
      sql,
      history_id: metadata.historyId,
      question: metadata.question,
      model: metadata.model,
      source: metadata.source ?? "manual",
    }),
  });
}

export function fetchExecutionJob(identifier: string): Promise<ExecutionJob> {
  return request<ExecutionJob>(`/api/query/jobs/${encodeURIComponent(identifier)}`);
}

export function cancelExecutionJob(identifier: string): Promise<ExecutionJob> {
  return request<ExecutionJob>(`/api/query/jobs/${encodeURIComponent(identifier)}`, { method: "DELETE" });
}

export async function exportQuery(
  connection: string,
  sql: string,
  format: "csv" | "json" | "markdown",
): Promise<void> {
  const response = await fetch("/api/query/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connection, sql, format }),
  });
  if (!response.ok) {
    const payload = (await response.json()) as { detail?: string };
    throw new Error(payload.detail ?? `Export failed (${response.status})`);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `asksql-results.${format}`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function reviewWrite(connection: string, sql: string): Promise<WriteReview> {
  return request<WriteReview>("/api/write/review", {
    method: "POST",
    body: JSON.stringify({ connection, sql }),
  });
}

export function commitWrite(connection: string, sql: string, token: string): Promise<ExecutionJob> {
  return request<ExecutionJob>("/api/write/commit", {
    method: "POST",
    body: JSON.stringify({ connection, sql, token }),
  });
}

export function explainQuery(connection: string, sql: string): Promise<{ columns: string[]; rows: unknown[][] }> {
  return request<{ columns: string[]; rows: unknown[][] }>(
    `/api/connections/${encodeURIComponent(connection)}/explain`,
    { method: "POST", body: JSON.stringify({ sql }) },
  );
}

export async function fetchHistory(connection?: string, search?: string): Promise<HistoryEntry[]> {
  const params = new URLSearchParams();
  if (connection) params.set("connection", connection);
  if (search) params.set("search", search);
  const payload = await request<{ history: HistoryEntry[] }>(`/api/history?${params}`);
  return payload.history;
}

export function pinHistory(identifier: string, pinned: boolean): Promise<HistoryEntry> {
  return request<HistoryEntry>(`/api/history/${encodeURIComponent(identifier)}/pin`, {
    method: "PATCH",
    body: JSON.stringify({ pinned }),
  });
}

export function deleteHistory(identifier: string): Promise<void> {
  return request<void>(`/api/history/${encodeURIComponent(identifier)}`, { method: "DELETE" });
}

export function clearHistory(connection?: string): Promise<void> {
  const suffix = connection ? `?connection=${encodeURIComponent(connection)}` : "";
  return request<void>(`/api/history${suffix}`, { method: "DELETE" });
}
