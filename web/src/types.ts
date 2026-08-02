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

export interface SetupStatus {
  ready: boolean;
  configDir: string;
  connections: number;
  connectionError: string;
  model: string;
  modelChecked: boolean;
  modelReady: boolean;
  modelDetail: string;
  nextSteps: string[];
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

export type QueryDocumentState = "draft" | "generated" | "running" | "completed" | "failed" | "cancelled";

export interface QueryDocument {
  id: string;
  title: string;
  connection: string;
  selected_tables: string[];
  question: string;
  generated_sql: string;
  edited_sql: string;
  lifecycle_state: QueryDocumentState;
  execution_status: QueryExecution["status"] | null;
  duration_ms: number | null;
  row_count: number | null;
  error: string | null;
  result_reference: string | null;
  created_at: string;
  updated_at: string;
  saved_query_id: string | null;
  parameter_values: Record<string, unknown>;
  semantic_model_id: string | null;
  semantic_plan: SemanticQueryPlan | null;
}

export interface WorkspaceSnapshot {
  activeConnection: string | null;
  activeDocumentId: string | null;
  documents: QueryDocument[];
}

export interface SavedQuery {
  id: string;
  name: string;
  description: string;
  connection_hint: string;
  natural_language_question: string;
  sql: string;
  schema_context: string[];
  tags: string[];
  folder: string | null;
  favorite: boolean;
  created_at: string;
  updated_at: string;
  source_document_id: string | null;
  parameters: SavedQueryParameter[];
}

export type SavedQueryParameterType = "text" | "integer" | "decimal" | "boolean" | "date" | "datetime";

export interface SavedQueryParameter {
  name: string;
  data_type: SavedQueryParameterType;
  required: boolean;
  default_value: unknown;
  description: string;
  sensitive: boolean;
}

export interface SavedQueryLibrary {
  savedQueries: SavedQuery[];
  folders: string[];
  tags: string[];
}

export interface SemanticEntity {
  name: string;
  source_table: string;
  primary_key: string;
  description: string;
}

export interface SemanticMetricFilter {
  column: string;
  operator: "eq" | "neq" | "gt" | "gte" | "lt" | "lte";
  value: unknown;
}

export interface SemanticMetric {
  name: string;
  label: string;
  description: string;
  entity: string;
  aggregation: "sum" | "count" | "count_distinct" | "average" | "minimum" | "maximum";
  expression: string;
  filters: SemanticMetricFilter[];
  format: string;
}

export interface SemanticDimension {
  name: string;
  label: string;
  description: string;
  entity: string;
  expression: string;
  data_type: string;
  time_granularities: string[];
}

export interface SemanticRelationship {
  name: string;
  from_entity: string;
  to_entity: string;
  from_column: string;
  to_column: string;
  join_type: "left" | "inner";
  cardinality: "many_to_one" | "one_to_many" | "one_to_one";
}

export interface SemanticModel {
  id: string;
  name: string;
  description: string;
  connection_hint: string;
  entities: SemanticEntity[];
  metrics: SemanticMetric[];
  dimensions: SemanticDimension[];
  relationships: SemanticRelationship[];
  created_at: string;
  updated_at: string;
}

export interface SemanticQueryPlan {
  model_id: string;
  metrics: string[];
  dimensions: { name: string; granularity: string | null }[];
  filters: Record<string, unknown>[];
}

export interface SemanticTraceItem {
  kind: "metric" | "dimension" | "relationship";
  name: string;
  sql: string;
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
