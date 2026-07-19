export interface ConnectionProfile {
  name: string;
  url: string;
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
}
