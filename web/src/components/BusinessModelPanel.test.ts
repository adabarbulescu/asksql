import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import { useStudioStore } from "../stores/studio";
import BusinessModelPanel from "./BusinessModelPanel.vue";

describe("BusinessModelPanel", () => {
  it("renders structured semantic definitions against the loaded schema", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const studio = useStudioStore();
    studio.selectedConnection = "local";
    studio.tables = [{
      name: "orders", columns: [
        { name: "id", type: "integer", primaryKey: true },
        { name: "total_amount", type: "decimal", primaryKey: false },
      ], foreignKeys: [], indexes: [], rowCount: 2,
    }];
    studio.semanticModels = [{
      id: "commerce", name: "Commerce", description: "", connection_hint: "local",
      entities: [{ name: "orders", source_table: "orders", primary_key: "id", description: "" }],
      metrics: [{ name: "revenue", label: "Revenue", description: "", entity: "orders", aggregation: "sum",
        expression: "total_amount", filters: [], format: "currency" }],
      dimensions: [], relationships: [], created_at: "", updated_at: "",
    }];
    studio.selectedSemanticModelId = "commerce";

    const wrapper = mount(BusinessModelPanel, { global: { plugins: [pinia] } });

    expect(wrapper.text()).toContain("Reusable metrics, dimensions and joins");
    expect((wrapper.find('input[aria-label="Metric label"]').element as HTMLInputElement).value).toBe("Revenue");
    expect(wrapper.text()).toContain("total_amount");
  });

  it("keeps a schema proposal as an unsaved review until Save is clicked", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const studio = useStudioStore();
    studio.selectedConnection = "local";
    const model = {
      name: "Suggested business model", description: "Draft", connection_hint: "local",
      entities: [{ name: "orders", source_table: "orders", primary_key: "id", description: "" }],
      metrics: [{ name: "revenue", label: "Revenue", description: "", entity: "orders", aggregation: "sum" as const,
        expression: "total", filters: [], format: "number" }],
      dimensions: [{ name: "order_date", label: "Order date", description: "", entity: "orders",
        expression: "created_at", data_type: "datetime", time_granularities: ["month"] }],
      relationships: [],
    };
    const draft = { state: "draft" as const, requires_review: true as const, model,
      suggestions: [{ path: "metrics.revenue", kind: "metric" as const, label: "Revenue",
        reason: "Numeric amount column", confidence: "high" as const }], warnings: [] };
    vi.spyOn(studio, "proposeBusinessModel").mockImplementation(async () => {
      studio.semanticDraft = draft;
      studio.semanticReadiness = {
        ready: false,
        checks: [{ code: "schema_valid", status: "passed", severity: "error",
          message: "All semantic references exist.", path: null }],
        workflows: [{ workflow: "metric_change_investigation", eligible: true, missing: [],
          compatible_metrics: ["revenue"], compatible_time_dimensions: ["order_date"] }],
        validation_queries: [],
        validation_results: [{ id: "freshness.order_date", title: "Freshness of Order date", status: "warning",
          severity: "warning", observed: "2025-01-01", message: "Latest value is 584 days old; threshold is 45.",
          sql: "select max(created_at) from orders", subject: { dimension: "order_date" } }],
      };
      return draft;
    });
    const save = vi.spyOn(studio, "saveSemanticModel").mockResolvedValue({
      ...model, id: "saved", created_at: "", updated_at: "",
    });

    const wrapper = mount(BusinessModelPanel, { global: { plugins: [pinia] } });
    await wrapper.find(".empty-semantic .primary-button").trigger("click");

    expect(wrapper.text()).toContain("Nothing is saved until you confirm it");
    expect(wrapper.text()).toContain("Numeric amount column");
    expect(wrapper.text()).toContain("Freshness of Order date");
    expect(wrapper.text()).toContain("584 days old");
    expect(save).not.toHaveBeenCalled();

    await wrapper.find("main footer .primary-button").trigger("click");
    expect(save).toHaveBeenCalledOnce();
    expect(save.mock.calls[0][1]).toBeUndefined();
  });
});
