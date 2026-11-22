import { test, expect } from "@playwright/test";

test("facility findings respect verdict precedence, ordering, and review counts", async ({ page }) => {
  await page.goto("/allergies");
  await page.getByRole("checkbox", { name: "Peanuts", exact: true }).check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Text", exact: true }).click();
  await page.locator("textarea").fill("label");
  const response = {
    ingredients_text: "label", ingredients: [{ name: "label", children: [] }], warnings: [],
    allergens: [
      { allergen: "milk", verdict: "confirmed", evidence_ingredient: "milk" },
      { allergen: "wheat", verdict: "inferable", evidence_ingredient: "wheat", reason_en: "Likely reason", explanation_en: "Extra explanation" },
      { allergen: "fish", verdict: "undecidable", evidence_ingredient: "fish", reason_en: "Unclear reason", explanation_en: null },
    ],
    shared_facility: [
      { allergen: "peanut", words: ["땅콩"], reason_en: "Facility reason" },
      { allergen: "milk", words: ["우유"], reason_en: "Should not appear" },
    ],
  };
  await page.route("**/analyze-text", route => route.fulfill({ json: response }));
  await page.getByRole("button", { name: "Analyze" }).click();
  const rows = page.locator(".result-row");
  await expect(rows.locator(".result-name")).toHaveText(["Milk", "Wheat", "Fish", "Peanuts", "Sesame", "Egg", "Shellfish", "Tree nuts", "Soy"]);
  await expect(page.locator(".result-banner")).toContainText("Analysis needs review");
  await expect(page.locator(".result-banner")).not.toContainText("results need review");
  await expect(page.locator(".result-banner")).toContainText("Made in a facility that also handles: Peanuts");
  const peanut = rows.filter({ hasText: "Peanuts" });
  await expect(peanut).toContainText("May contain");
  await expect(peanut).toContainText("Shared facility");
  await expect(peanut.getByText("Shared facility", { exact: true })).toBeHidden();
  await peanut.locator("summary").click();
  await expect(peanut.getByText("Shared facility", { exact: true })).toBeVisible();
  await expect(peanut.locator(".result-reason > p").first()).toHaveText("Facility reason");
  const wheat = rows.filter({ hasText: "Wheat" });
  await wheat.locator("summary").click();
  await expect(wheat.locator(".result-reason > p")).toHaveText(["Likely reason", "AI explanation: Extra explanation"]);
  const fish = rows.filter({ hasText: "Fish" });
  await fish.locator("summary").click();
  await expect(fish.locator(".result-explanation")).toHaveCount(0);
  await expect(page.getByText("Should not appear")).toHaveCount(0);

  await page.getByRole("button", { name: "Scan Another" }).click();
  await page.unroute("**/analyze-text");
  await page.route("**/analyze-text", route => route.fulfill({ json: { ...response, warnings: ["OCR incomplete"] } }));
  await page.getByRole("button", { name: "Text", exact: true }).click();
  await page.locator("textarea").fill("label");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(rows.filter({ hasText: "Peanuts" })).toContainText("Cannot determine");
  await rows.filter({ hasText: "Peanuts" }).locator("summary").click();
  await expect(rows.filter({ hasText: "Peanuts" }).locator(".result-reason > p").first()).toContainText("label could not be fully analyzed");
  await expect(rows.filter({ hasText: "Peanuts" }).locator(".facility-note")).toContainText("Facility reason");
});

test("facility-only selection has a clear banner and consistent badges", async ({ page }) => {
  await page.goto("/allergies");
  await page.getByRole("checkbox", { name: "Peanuts", exact: true }).check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Text", exact: true }).click();
  await page.locator("textarea").fill("label");
  await page.route("**/analyze-text", route => route.fulfill({ json: {
    ingredients_text: "label", ingredients: [{ name: "label", children: [] }], warnings: [],
    allergens: [
      { allergen: "soy", verdict: "inferable", evidence_ingredient: "soy", reason_en: "Possible soy" },
      { allergen: "fish", verdict: "undecidable", evidence_ingredient: "fish", reason_en: "Unclear fish" },
    ],
    shared_facility: [{ allergen: "peanut", words: ["peanut"], reason_en: "Facility reason" }],
  } }));
  await page.getByRole("button", { name: "Analyze" }).click();
  const banner = page.locator(".result-banner");
  await expect(banner).toContainText("Made in a facility that also handles: Peanuts");
  await expect(banner).not.toContainText("No selected allergens detected");
  await expect(banner).not.toContainText("results need review");
  const badges = page.locator(".badge.inferable, .badge.undecidable, .badge.shared_facility");
  await expect(badges).toHaveCount(3);
  const styles = await badges.evaluateAll((elements) => elements.map((element) => ({
    width: element.getBoundingClientRect().width,
    transform: getComputedStyle(element).textTransform,
    height: element.getBoundingClientRect().height,
  })));
  expect(new Set(styles.map((style) => style.width)).size).toBe(1);
  expect(new Set(styles.map((style) => style.height)).size).toBe(1);
  expect(styles.every((style) => style.transform === "none")).toBe(true);
  await expect(page.locator(".result-row.highlighted")).toContainText("Peanuts");
});
