import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it } from "vitest";

import { useStudioStore } from "../stores/studio";
import ParameterForm from "./ParameterForm.vue";

describe("ParameterForm", () => {
  it("generates typed controls and keeps values on the active document", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const studio = useStudioStore();
    studio.documents = [{
      id: "document", title: "Report", connection: "local", selected_tables: [], question: "",
      generated_sql: "", edited_sql: "select :start_date, :secret", lifecycle_state: "draft",
      execution_status: null, duration_ms: null, row_count: null, error: null, result_reference: null,
      created_at: "", updated_at: "", saved_query_id: "saved", parameter_values: {},
      semantic_model_id: null, semantic_plan: null,
    }];
    studio.activeDocumentId = "document";
    studio.savedQueries = [{
      id: "saved", name: "Report", description: "", connection_hint: "local", natural_language_question: "",
      sql: "select :start_date, :secret", schema_context: [], tags: [], folder: null, favorite: false,
      created_at: "", updated_at: "", source_document_id: "document", parameters: [
        { name: "start_date", data_type: "date", required: true, default_value: "2026-08-01", description: "Start date", sensitive: false },
        { name: "secret", data_type: "text", required: true, default_value: null, description: "Secret", sensitive: true },
      ],
    }];
    const wrapper = mount(ParameterForm, { global: { plugins: [pinia] } });

    const inputs = wrapper.findAll("input");
    expect(inputs[0].attributes("type")).toBe("date");
    expect(inputs[1].attributes("type")).toBe("password");
    await inputs[0].setValue("2026-09-01");
    expect(studio.activeDocument?.parameter_values.start_date).toBe("2026-09-01");
  });
});
