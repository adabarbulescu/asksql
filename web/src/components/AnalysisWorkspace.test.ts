import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";

import { useStudioStore } from "../stores/studio";
import AnalysisWorkspace from "./AnalysisWorkspace.vue";

describe("AnalysisWorkspace", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("offers only an available, semantic-backed workflow", () => {
    const studio = useStudioStore();
    studio.selectedSemanticModelId = "model";
    studio.analysisTemplates = [{ id: "revenue_investigation", name: "Revenue Investigation",
      description: "Explain the change", goal: "Explain revenue", available: true, estimated_queries: 8 }];
    const wrapper = mount(AnalysisWorkspace);
    expect(wrapper.text()).toContain("What do you want to understand?");
    expect(wrapper.text()).toContain("8 governed semantic queries");
    expect(wrapper.text()).not.toContain("Sales Overview");
  });

  it("renders conclusions with evidence and export controls", () => {
    const studio = useStudioStore();
    studio.activeAnalysisRun = {
      id: "run", definition_id: "definition", definition_name: "Revenue Investigation",
      definition_snapshot: {} as never, semantic_model_id: "model", semantic_model_snapshot: {} as never, input_values: {},
      state: "completed", steps: [], evidence: [{ id: "evidence", step_id: "change.current",
        title: "Current revenue", semantic_plan: { model_id: "model", metrics: ["revenue"], dimensions: [], filters: [] },
        compiled_sql: "select sum(total)", parameters: {}, columns: ["revenue"], rows: [[140]], row_count: 1,
        duration_ms: 3.2, status: "succeeded", error: null, quality_flags: [] }],
      findings: [{ id: "change", title: "Revenue change", claim: "Revenue decreased by 6.7%.", magnitude: -10,
        finding_type: "diagnostic", direction: "decreased", evidence_ids: ["evidence"], method: "deterministic_comparison" }],
      charts: [], report: { headline: "Revenue decreased by 6.7%.", summary: "Orders were lower.", confidence: "high",
        confidence_score: 92, confidence_basis: { evidence_coverage: 100, data_completeness: 78 } }, error: null,
      parent_run_id: null, created_at: "2026-08-02T10:00:00Z", updated_at: "2026-08-02T10:00:01Z",
      completed_at: "2026-08-02T10:00:01Z",
    };
    const wrapper = mount(AnalysisWorkspace);
    expect(wrapper.text()).toContain("92%");
    expect(wrapper.text()).toContain("Deterministic comparisons, not generated assertions");
    expect(wrapper.text()).toContain("select sum(total)");
    expect(wrapper.text()).toContain("Export PDF");
  });
});
