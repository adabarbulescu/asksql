import { describe, expect, it } from "vitest";

import { requestErrorMessage } from "./api";

describe("requestErrorMessage", () => {
  it("formats FastAPI validation errors", () => {
    expect(
      requestErrorMessage(
        { detail: [{ loc: ["body", "url"], msg: "Field required" }] },
        422,
      ),
    ).toBe("body.url: Field required");
  });
});
