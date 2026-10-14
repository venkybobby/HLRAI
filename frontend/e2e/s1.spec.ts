import { expect, test } from "@playwright/test";

// Slice S1 end-to-end: the gate is visible everywhere an automated conclusion could appear.
test("overview shows the blocked banner and migration progress", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("blocked-banner")).toContainText("Blocked: 5 of 5 readings unverified");
  await expect(page.getByTestId("stat-obligations")).toHaveText("5");
  await expect(page.getByTestId("stat-migrated")).toHaveText("6 of 69");
  await expect(page.getByTestId("who")).toContainText("Venky R");
  await expect(page.getByText("Not legal advice")).toBeVisible();
});

test("register lists obligations, none verified, and evaluations show now vs if verified", async ({ page }) => {
  await page.goto("/register");
  const rows = page.getByTestId("obligations").locator("tbody tr");
  await expect(rows).toHaveCount(5);
  await expect(page.getByTestId("obligations").getByText("verified primary", { exact: false })).toHaveCount(0);
  const ev = page.getByTestId("evaluations").locator("tbody tr");
  await expect(ev).toHaveCount(4);
  await expect(ev.first()).toContainText("blocked_unverified_interpretation / undetermined");
  await expect(ev.first()).toContainText("open / permitted");
});

test("obligation detail explains why it is blocked and who could unblock it", async ({ page }) => {
  await page.goto("/register");
  await page.getByRole("link", { name: "OBL-ART50-2" }).click();
  await expect(page).toHaveURL(/\/obligations\/OBL-ART50-2$/);
  await expect(page.getByTestId("blocked-reason")).toContainText("verified_primary");
  await expect(page.getByText("Reviewer: none")).toBeVisible();
  await expect(page.getByText("CTL-MARK-DETECT")).toBeVisible();
});

test("unknown obligation shows the contract error code, not a blank page", async ({ page }) => {
  await page.goto("/obligations/NOPE");
  await expect(page.getByRole("alert")).toContainText("not_found");
});

test("revisions lists the baseline revision", async ({ page }) => {
  await page.goto("/revisions");
  await expect(page.getByTestId("revisions").locator("tbody tr")).toHaveCount(1);
  await expect(page.getByText("(current)")).toBeVisible();
  await expect(page.getByText("Only the baseline exists")).toBeVisible();
});
