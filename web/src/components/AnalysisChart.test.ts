import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AnalysisChart from "./AnalysisChart.vue";

describe("AnalysisChart", () => {
  it("renders source-backed bars and accessible labels", () => {
    const wrapper = mount(AnalysisChart, { props: { chart: {
      id: "chart", type: "bar", title: "Revenue contribution", labels: ["DE", "FR"],
      series: [{ name: "Contribution", values: [-30, 20] }], evidence_ids: ["evidence"],
    } } });
    expect(wrapper.get("svg").attributes("aria-label")).toBe("Revenue contribution");
    expect(wrapper.findAll("rect.chart-bar")).toHaveLength(2);
    expect(wrapper.find("rect.negative").exists()).toBe(true);
  });
});
