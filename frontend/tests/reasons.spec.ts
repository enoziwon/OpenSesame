import { test, expect } from "@playwright/test";

const fallback = "The reason could not be provided. Please check the original label.";

test("server reasons survive normalization, missing reasons use neutral fallback", async ({ page }) => {
  await page.goto("/scan");
  const path = "/src/utils/analysis.ts";
  const reasons = ["", "   ", undefined, "A product-specific reason. ".repeat(45)];
  for (const reason of reasons) {
    await page.route("**/analyze-text", route => route.fulfill({ json: {
      ingredients_text: "source", ingredients: [{ name: "source", children: [] }], warnings: [],
      allergens: [
        { allergen: "wheat", verdict: "inferable", evidence_ingredient: "source", reason_en: reason,
          basis: ["LIKELY"], species: [], evidence_en: "source", reason_ko: "판정 사유" },
        { allergen: "fish", verdict: "undecidable", evidence_ingredient: "source" },
        { allergen: "soy", verdict: "confirmed", evidence_ingredient: "soy", reason_en: "Confirmed reason must not appear." },
      ],
    } }));
    await page.getByRole("button", { name: "Enter ingredient text" }).click();
    await page.locator("textarea").fill("source");
    await page.getByRole("button", { name: "Analyze" }).click();
    const wheat = page.locator("details.result-row").filter({ hasText: "Wheat" });
    const fish = page.locator("details.result-row").filter({ hasText: "Fish" });
    await wheat.locator("summary").click();
    await fish.locator("summary").click();
    await expect(wheat.locator(".result-reason > p").first()).toHaveText(reason?.trim() ? reason : fallback);
    await expect(fish.locator(".result-reason")).toContainText(fallback);
    await expect(page.getByText("Confirmed reason must not appear.", { exact: true })).toHaveCount(0);
    await expect(page.locator(".result-row")).toHaveCount(9);
    await expect(page.locator(".result-row").filter({ hasText: "Soy" }).locator("summary, .result-chevron")).toHaveCount(0);
    const geometry = await wheat.locator(".result-reason").evaluate(el => ({
      height: el.clientHeight, scrollHeight: el.scrollHeight, width: el.clientWidth, scrollWidth: el.scrollWidth,
    }));
    expect(geometry.scrollHeight).toBeLessThanOrEqual(geometry.height);
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width);
    await page.getByRole("button", { name: "Scan Another" }).click();
    await page.unroute("**/analyze-text");
  }
  const normalized = await page.evaluate(async path => {
    const { normalizeAnalysis } = await import(path);
    return normalizeAnalysis({
      ingredients_text: "source", ingredients: [{ name: "source", children: [] }], warnings: [],
      allergens: [{ allergen: "wheat", verdict: "inferable", evidence_ingredient: "source",
        reason_en: "  Exact server sentence.  ", basis: ["LIKELY"], species: ["wheat"],
        evidence_en: "source", reason_ko: "원문 사유" }],
    }).allergens[0];
  }, path);
  expect(normalized).toMatchObject({ reason_en: "  Exact server sentence.  ", basis: ["LIKELY"],
    species: ["wheat"], evidence_en: "source", reason_ko: "원문 사유" });
});
