import { mount } from "@vue/test-utils";
import { beforeAll, describe, expect, it } from "vitest";

import ResultsGrid from "./ResultsGrid.vue";

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
    unobserve() {}
  };
});

describe("ResultsGrid", () => {
  it("renders a bounded virtual window for large results", () => {
    const rows = Array.from({ length: 1000 }, (_, index) => [index]);
    const wrapper = mount(ResultsGrid, {
      props: {
        loading: false,
        execution: {
          sql: "select n",
          status: "succeeded",
          durationMs: 1,
          error: null,
          result: { columns: ["n"], rows, truncated: false, limit: 1000 },
        },
      },
    });

    expect(wrapper.findAll("tbody tr").length).toBeLessThan(40);
    expect(wrapper.text()).toContain("0");
  });
});
