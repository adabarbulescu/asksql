import { expect, test, type APIResponse } from "@playwright/test";

async function jsonResponse<T>(response: APIResponse): Promise<T> {
  const body = await response.text();
  expect(response.ok(), body).toBeTruthy();
  return JSON.parse(body) as T;
}

function monthStart(offset: number): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + offset, 1)).toISOString().slice(0, 10);
}

test("opens the packaged Studio and its primary dialogs", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("AskSQL", { exact: true })).toBeVisible();
  await expect(page.getByText("Studio", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Model/ }).click();
  await expect(page.getByRole("heading", { name: "AI model" })).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  const addDatabase = page.getByRole("button", { name: /Add existing database/ });
  if (await addDatabase.isVisible()) {
    await addDatabase.click();
    await expect(page.getByRole("heading", { name: "Add a database" })).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();
  }
});

test("carries a demo analysis from governed model to exportable evidence", async ({ page, request }) => {
  const existing = await jsonResponse<{ connections: { name: string }[] }>(await request.get("/api/connections"));
  if (existing.connections.some((connection) => connection.name === "demo")) {
    const removed = await request.delete("/api/connections/demo");
    expect(removed.ok(), await removed.text()).toBeTruthy();
  }
  await jsonResponse(await request.post("/api/connections/demo"));
  const proposal = await jsonResponse<{ state: string; requires_review: boolean }>(
    await request.post("/api/semantic-models/propose", { data: { connection: "demo" } }),
  );
  expect(proposal).toMatchObject({ state: "draft", requires_review: true });

  const models = await jsonResponse<{ semanticModels: Record<string, unknown>[] }>(
    await request.get("/api/semantic-models?connection=demo"),
  );
  const model = models.semanticModels[0];
  expect(model).toBeDefined();
  const { id, created_at: _createdAt, updated_at: _updatedAt, ...modelInput } = model;
  expect(typeof id).toBe("string");

  const readiness = await jsonResponse<{
    ready: boolean;
    workflows: {
      workflow: string;
      eligible: boolean;
      compatible_metrics: string[];
      compatible_time_dimensions: string[];
    }[];
  }>(await request.post("/api/semantic-models/readiness", { data: modelInput }));
  const workflow = readiness.workflows.find((item) => item.workflow === "metric_change_investigation");
  expect(readiness.ready).toBeTruthy();
  expect(workflow?.eligible).toBeTruthy();
  expect(workflow?.compatible_metrics.length).toBeGreaterThan(0);
  expect(workflow?.compatible_time_dimensions.length).toBeGreaterThan(0);
  const metricName = workflow?.compatible_metrics[0] ?? "";
  const timeDimensionName = workflow?.compatible_time_dimensions[0] ?? "";

  const templates = await jsonResponse<{ templates: { id: string; available: boolean }[] }>(
    await request.get(`/api/analysis-templates?semantic_model_id=${id}`),
  );
  expect(templates.templates).toContainEqual(
    expect.objectContaining({ id: "metric_change_investigation", available: true }),
  );

  const definition = await jsonResponse<{ id: string }>(await request.post("/api/analysis-definitions/from-template", {
    data: {
      semantic_model_id: id,
      template: "metric_change_investigation",
      metric_name: metricName,
      time_dimension_name: timeDimensionName,
    },
  }));
  const started = await jsonResponse<{ id: string }>(await request.post("/api/analysis-runs", {
    data: {
      definition_id: definition.id,
      input_values: {
        current_start: monthStart(-1),
        current_end: monthStart(0),
        previous_start: monthStart(-2),
        previous_end: monthStart(-1),
      },
    },
  }));

  let completed: { state: string; evidence: unknown[] } | undefined;
  await expect.poll(async () => {
    completed = await jsonResponse(await request.get(`/api/analysis-runs/${started.id}`));
    return completed.state;
  }, { timeout: 10_000 }).toMatch(/^(completed|partially_completed)$/);
  expect(completed?.evidence.length).toBeGreaterThan(0);

  const exported = await request.get(`/api/analysis-runs/${started.id}/export?format=html`);
  expect(exported.ok(), await exported.text()).toBeTruthy();
  expect(exported.headers()["content-type"]).toContain("text/html");
  expect(exported.headers()["content-disposition"]).toContain(`asksql-analysis-${started.id}.html`);

  await page.goto("/?connection=demo");
  await expect(page.getByRole("button", { name: /demo\s+SQLite/i })).toBeVisible();
  await expect(page.getByText("2 tables", { exact: true })).toBeVisible();
  await expect(page.getByText("Evidence", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export HTML" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export PDF" })).toBeVisible();
});
