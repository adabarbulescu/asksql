import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import SchemaTree from "./SchemaTree.vue";

const tables = [{
  name: "orders",
  rowCount: 12,
  columns: [{ name: "customer_id", type: "integer", primaryKey: false }],
  foreignKeys: [{ column: "customer_id", referencedTable: "customers", referencedColumn: "id" }],
  indexes: [{ name: "orders_customer", columns: ["customer_id"], unique: false }],
}];

describe("SchemaTree", () => {
  it("searches metadata and emits context selection", async () => {
    const wrapper = mount(SchemaTree, { props: { tables, loading: false, selected: ["orders"] } });
    expect(wrapper.text()).toContain("orders");
    expect(wrapper.text()).toContain("12 rows");

    await wrapper.get('input[type="checkbox"]').setValue(false);
    expect(wrapper.emitted("toggle")?.[0]).toEqual(["orders"]);

    await wrapper.get('input[aria-label="Search schema"]').setValue("missing");
    expect(wrapper.text()).toContain("No schema matches");
  });
});
