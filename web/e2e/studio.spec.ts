import { expect, test } from "@playwright/test";

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
