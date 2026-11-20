import { test, expect } from "@playwright/test";

const analysis = {
  ingredients_text: "peanut, sesame, milk products, mixed grain powder",
  ingredients: [{ name: "peanut", children: [] }],
  allergens: [
    { allergen: "peanut", verdict: "confirmed", evidence_ingredient: "peanut" },
    { allergen: "sesame", verdict: "confirmed", evidence_ingredient: "sesame" },
    {
      allergen: "milk",
      verdict: "inferable",
      evidence_ingredient: "milk products",
      reason_en:
        "Milk may be present because the ingredient source has not been fully specified.",
    },
    {
      allergen: "wheat",
      verdict: "undecidable",
      evidence_ingredient: "mixed grain powder",
      reason_en:
        "The ingredient “mixed grain powder” does not specify whether wheat is included.",
    },
  ],
  warnings: [],
};

for (const width of [375, 320]) {
  test(`results accordions and bounded scrolling at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 812 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "opensesame.allergies",
        JSON.stringify(["peanut", "sesame", "milk", "wheat"]),
      ),
    );
    await page.route("**/analyze", (route) =>
      route.fulfill({ json: analysis }),
    );
    await page.goto("/scan");
    await page
      .locator("input[type=file]")
      .nth(1)
      .setInputFiles({
        name: "label.svg",
        mimeType: "image/svg+xml",
        buffer: Buffer.from(
          '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>',
        ),
      });
    await page.getByRole("button", { name: "Analyze" }).click();
    await expect(page.getByRole("status")).toContainText(
      "2 confirmed · 2 results need review.",
    );
    const milk = page.locator("details.result-row").filter({ hasText: "Milk" });
    const wheat = page
      .locator("details.result-row")
      .filter({ hasText: "Wheat" });
    await expect(page.locator(".result-row")).toHaveCount(9);
    await expect(milk).not.toHaveAttribute("open", "");
    await expect(wheat).not.toHaveAttribute("open", "");
    await page.screenshot({
      path: `test-results/results-collapsed-${width}.png`,
    });
    await milk.locator("summary").click();
    await expect(milk.locator(".result-reason")).toContainText(
      analysis.allergens[2].reason_en!,
    );
    await page.screenshot({ path: `test-results/results-milk-${width}.png` });
    await wheat.locator("summary").click();
    await expect(milk).toHaveAttribute("open", "");
    await expect(wheat.locator(".result-reason")).toContainText(
      analysis.allergens[3].reason_en!,
    );
    await page.screenshot({ path: `test-results/results-both-${width}.png` });
    await milk.locator("summary").click();
    await expect(wheat).toHaveAttribute("open", "");
    await page.screenshot({ path: `test-results/results-wheat-${width}.png` });
    await wheat.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(wheat).not.toHaveAttribute("open", "");
    for (const icon of await page
      .locator(".result-icon, .result-chevron")
      .all()) {
      expect(
        await icon.evaluate(
          (el: HTMLImageElement) =>
            el.complete &&
            el.naturalWidth > 0 &&
            el.width === el.naturalWidth &&
            el.height === el.naturalHeight,
        ),
      ).toBe(true);
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const actions = await page.locator(".result-actions").boundingBox();
    expect(actions!.y + actions!.height).toBeLessThanOrEqual(812);
    await page.getByText("Original ingredient text", { exact: true }).click();
    await expect(page.locator(".original-text")).toHaveText(
      analysis.ingredients_text,
    );
    await page.getByRole("button", { name: "Scan Another" }).click();
    await expect(page).toHaveURL(/scan$/);
  });
}
