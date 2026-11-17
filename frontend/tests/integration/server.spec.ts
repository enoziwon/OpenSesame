import { test, expect } from "@playwright/test";

test("ingredient input uses the official final server and renders its verdicts", async ({ page }) => {
  await page.goto("/scan");
  await page.getByRole("button", { name: "Enter ingredient text" }).click();
  await page.getByRole("textbox", { name: "Ingredient label text" }).fill(
    "원재료명: 소맥분(밀), 탈지분유, 설탕 / 밀, 우유 함유",
  );
  const pending = page.waitForResponse(r => r.url().endsWith("/analyze-text"));
  await page.getByRole("button", { name: "Analyze" }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toEqual({ text: "원재료명: 소맥분(밀), 탈지분유, 설탕 / 밀, 우유 함유" });
  const result = await response.json();
  expect(result.meta).toMatchObject({ ocr_engine: "text", classifier: "final-lexicon-v1" });
  await expect(page).toHaveURL(/results$/);
  for (const name of ["Milk", "Wheat"]) {
    await expect(page.locator(".result-row").filter({ hasText: name })).toContainText("Confirmed");
  }
  await expect(page.locator(".result-row").filter({ hasText: "Peanuts" })).toContainText("Not detected");
  await page.getByText("Original ingredient text", { exact: true }).click();
  await expect(page.locator(".original-text")).toContainText("탈지분유");
});

test("real product photo runs through CLOVA and the final server", async ({ page }) => {
  const photo = process.env.OPENSESAME_TEST_PHOTO;
  test.skip(!photo, "Set OPENSESAME_TEST_PHOTO to a real product label image; CLOVA credentials are required in root .env.");
  await page.goto("/scan");
  await page.locator("input[type=file]").nth(1).setInputFiles(photo!);
  const pending = page.waitForResponse(r => r.url().endsWith("/analyze"));
  await page.getByRole("button", { name: "Analyze" }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.meta).toMatchObject({ ocr_engine: "clova", classifier: "final-lexicon-v1" });
  expect(result.ingredients_text.trim()).not.toBe("");
  expect(result.ingredients.length).toBeGreaterThan(0);
  const expected = (process.env.OPENSESAME_TEST_EXPECTED_ALLERGENS || "")
    .split(",").map(value => value.trim()).filter(Boolean);
  for (const allergen of expected) {
    expect(result.allergens).toEqual(expect.arrayContaining([
      expect.objectContaining({ allergen, verdict: "confirmed" }),
    ]));
  }
  await expect(page).toHaveURL(/results$/);
  await page.getByText("Original ingredient text", { exact: true }).click();
  await expect(page.locator(".original-text")).toHaveText(result.ingredients_text);
  for (const finding of result.allergens) {
    await expect(page.locator(".evidence").filter({ hasText: finding.evidence_ingredient }).first()).toBeVisible();
  }
  console.info("Live photo analysis:", JSON.stringify({
    engine: result.meta.ocr_engine,
    classifier: result.meta.classifier,
    ingredients: result.ingredients.length,
    verdicts: result.allergens.map(({ allergen, verdict }: { allergen: string; verdict: string }) => ({ allergen, verdict })),
    warnings: result.warnings.length,
  }));
});
