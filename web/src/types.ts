export interface ConnectionProfile {
  name: string;
  url: string;
}

export interface ConnectionTest {
  valid: boolean;
  url: string;
  tables: number;
}

export interface ModelStatus {
  model: string;
  ready: boolean;
  detail: string;
}

export interface HistoryEntry {
  id: string;
  connection: string;
  question: string | null;
  sql: string;
  source: "ai" | "manual";
  model: string | null;
  created_at: string;
  updated_at: string;
  status: string;
  duration_ms: number | null;
  row_count: number | null;
  affected_rows: number | null;
  error: string | null;
  pinned: boolean;
}

export interface Column {
  name: string;
  type: string;
  primaryKey: boolean;
}

export interface ForeignKey {
  column: string;
  referencedTable: string;
  referencedColumn: string;
}

export interface TableSchema {
  name: string;
  columns: Column[];
  foreignKeys: ForeignKey[];
  indexes: { name: string; columns: string[]; unique: boolean }[];
  rowCount: number | null;
}

export interface DatabaseObject {
  name: string;
  kind: "view" | "trigger";
  table: string | null;
  sql: string | null;
}

export interface SchemaDetails {
  connection: string;
  tables: TableSchema[];
  views: DatabaseObject[];
  triggers: DatabaseObject[];
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  limit: number;
}

export interface QueryExecution {
  sql: string;
  status: "succeeded" | "refused" | "failed" | "timed_out" | "cancelled";
  durationMs: number;
  error: string | null;
  result?: QueryResult;
  mutation?: {
    affectedRows: number;
    lastInsertId: number | null;
  };
  historyId?: string;
}

export interface ExecutionJob {
  jobId: string;
  historyId: string;
  state: "queued" | "running" | "cancelling" | "completed";
  execution?: QueryExecution;
}

export interface WriteReview {
  token: string;
  expiresAt: string;
  statement: string;
}
