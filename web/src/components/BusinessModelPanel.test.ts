import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it } from "vitest";

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
});
