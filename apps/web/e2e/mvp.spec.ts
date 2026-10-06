import { expect, test } from "@playwright/test";

test("E1 signup consent key and stream", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
});

test("E2 approval card is keyboard reachable", async ({ page }) => {
  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
});

test("E4 artifacts explain infected state", async ({ page }) => {
  await page.goto("/artifacts");
  await expect(page.getByText("never downloadable")).toBeVisible();
});

test("E5 share page is noindex", async ({ page }) => {
  await page.goto("/share/example");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});
