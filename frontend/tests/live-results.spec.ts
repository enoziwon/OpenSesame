import { test, expect } from "@playwright/test";

test("different photo responses replace ingredient evidence and verdicts", async ({ page }) => {
  let calls = 0;
  await page.route("**/analyze", async (route) => {
    expect(route.request().postDataBuffer()?.toString()).toContain('name="file"');
    const milk = calls++ === 0;
    await route.fulfill({ json: {
      ingredients_text: milk ? "탈지분유" : "소맥분",
      ingredients: [{ name: milk ? "탈지분유" : "소맥분", children: [] }],
      allergens: [{ allergen: milk ? "milk" : "wheat", verdict: "confirmed",
        evidence_ingredient: milk ? "탈지분유" : "소맥분" }],
      warnings: [], meta: { ocr_engine: "clova", classifier: "llm" },
    } });
  });
  for (const [index, detected, absent, ingredient] of [
    [1, "Milk", "Wheat", "탈지분유"], [2, "Wheat", "Milk", "소맥분"],
  ] as const) {
    await page.goto("/scan");
    await page.locator("input[type=file]").nth(1).setInputFiles({
      name: `photo-${index}.svg`, mimeType: "image/svg+xml",
      buffer: Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${index * 10}" height="10"/>`),
    });
    await page.getByRole("button", { name: "Analyze" }).click();
    await expect(page.locator(".result-row").filter({ hasText: detected })).toContainText("Contains");
    await expect(page.locator(".result-row").filter({ hasText: absent })).toContainText("Not detected");
    await page.getByText("Original ingredient text", { exact: true }).click();
    await expect(page.locator(".original-text")).toHaveText(ingredient);
  }
  expect(calls).toBe(2);
});

test("mock OCR results are clearly marked as demo data", async ({ page }) => {
  await page.route("**/analyze", route => route.fulfill({ json: {
    ingredients_text: "sample", ingredients: [{ name: "sample", children: [] }],
    allergens: [], warnings: [], meta: { ocr_engine: "mock", classifier: "llm" },
  } }));
  await page.goto("/scan");
  await page.locator("input[type=file]").nth(1).setInputFiles({
    name: "label.svg", mimeType: "image/svg+xml",
    buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'),
  });
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByRole("alert")).toContainText("Demo analysis: sample data");
  await expect(page).toHaveURL(/results$/);
});
