import { test, expect } from "@playwright/test";
import fs from "node:fs";
const sample = JSON.parse(
  fs.readFileSync("../src/app/sample_response.json", "utf8"),
);
const image = {
  name: "label.svg",
  mimeType: "image/svg+xml",
  buffer: Buffer.from(
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><rect width="100" height="50" fill="orange"/></svg>',
  ),
};
for (const [width, height] of [
  [375, 812],
  [360, 800],
  [393, 852],
])
  test(`mobile flow ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await expect(page.getByRole("heading")).toHaveText(
      "Check Korean Foodfor Your Allergies",
    );
    await page.screenshot({ path: `test-results/landing-${width}.png` });
    await page.getByRole("button", { name: "Get Started" }).click();
    for (const checkbox of await page.getByRole("checkbox").all()) {
      await checkbox.check();
      await expect(checkbox).toBeChecked();
      await checkbox.uncheck();
      await expect(checkbox).not.toBeChecked();
    }
    await page.getByRole("checkbox", { name: "Milk", exact: true }).check();
    await page.getByRole("checkbox", { name: "Sesame", exact: true }).check();
    await page.screenshot({ path: `test-results/allergies-${width}.png` });
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.locator('input[capture="environment"]')).toHaveAttribute(
      "accept",
      "image/*",
    );
    await page.locator("input[type=file]").nth(1).setInputFiles(image);
    await expect(page.getByAltText("Selected ingredient label")).toBeVisible();
    await page.getByRole("button", { name: "Remove image" }).click();
    await expect(page.getByAltText("Selected ingredient label")).toHaveCount(0);
    await page.locator("input[type=file]").nth(1).setInputFiles(image);
    await page.screenshot({ path: `test-results/scan-${width}.png` });
    let calls = 0;
    await page.route("**/analyze", async (route) => {
      calls++;
      const body = route.request().postDataBuffer()!.toString();
      expect(body).toContain('name="file"');
      expect(body.match(/name="/g)?.length).toBe(2);
      expect(body).not.toContain("opensesame.allergies");
      await route.fulfill({ json: sample });
    });
    await page.getByRole("button", { name: "Analyze", exact: false }).click();
    await expect(
      page.getByRole("heading", { name: "Results", exact: true }),
    ).toBeVisible();
    expect(calls).toBe(1);
    await expect(page.getByText("Not detected", { exact: true })).toHaveCount(
      4,
    );
    await expect(page.getByText(/Demo analysis/)).toBeVisible();
    await expect(page.getByText("탈지분유", { exact: true })).toBeVisible();
    await page.screenshot({
      path: `test-results/results-${width}.png`,
      fullPage: true,
    });
    for (const path of ["/", "/allergies", "/scan", "/results"]) {
      await page.goto(path);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await page.goto("/allergies");
    await expect(
      page.getByRole("checkbox", { name: "Milk", exact: true }),
    ).toBeChecked();
    await page.reload();
    await expect(
      page.getByRole("checkbox", { name: "Milk", exact: true }),
    ).toBeChecked();
  });
test("optional fields, uncertain results, errors and request locking", async ({
  page,
}) => {
  await page.goto("/scan");
  await page
    .locator("input[type=file]")
    .nth(1)
    .setInputFiles({
      name: "bad.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("bad"),
    });
  await expect(page.getByRole("alert")).toContainText("Choose an image");
  await page.locator("input[type=file]").nth(1).setInputFiles(image);
  await page.route("**/analyze", (route) => route.fulfill({ status: 500 }));
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByRole("alert")).toContainText("500");
  await page.unroute("**/analyze");
  let calls = 0;
  await page.route("**/analyze", async (route) => {
    calls++;
    await new Promise((r) => setTimeout(r, 300));
    await route.fulfill({
      json: {
        ingredients_text: "향료",
        ingredients: [{ name: "향료", children: [] }],
        allergens: [
          {
            allergen: "milk",
            verdict: "undecidable",
            evidence_ingredient: "향료",
          },
        ],
        warnings: ["Classification incomplete"],
      },
    });
  });
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByRole("button", { name: "Analyzing…" })).toBeDisabled();
  await expect(
    page.getByText("Cannot determine", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Classification incomplete", { exact: true }),
  ).toBeVisible();
  expect(calls).toBe(1);
  await expect(page.getByText(/Demo analysis/)).toHaveCount(0);
});
test("real FastAPI mock endpoint", async ({ page }) => {
  await page.goto("/allergies");
  await page.getByRole("checkbox", { name: "Milk", exact: true }).check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.locator("input[type=file]").nth(1).setInputFiles(image);
  const response = page.waitForResponse((r) => r.url().endsWith("/analyze"));
  await page.getByRole("button", { name: "Analyze" }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByText(/Demo analysis/)).toBeVisible();
  await expect(page.getByText("탈지분유", { exact: true })).toBeVisible();
});

test("file limits, drag and drop, malformed responses and local assets", async ({
  page,
}) => {
  await page.goto("/allergies");
  await expect(page.locator(".allergen-icon")).toHaveCount(9);
  for (const icon of await page.locator(".allergen-icon").all()) {
    expect(
      await icon.evaluate(
        (el: HTMLImageElement) =>
          el.complete &&
          el.naturalWidth > 0 &&
          el.width === 35 &&
          el.height === 35,
      ),
    ).toBe(true);
  }
  await page.goto("/scan");
  const upload = page.locator("input[type=file]").nth(1);
  await upload.setInputFiles({
    name: "large.png",
    mimeType: "image/png",
    buffer: Buffer.alloc(10 * 1024 * 1024 + 1),
  });
  await expect(page.getByRole("alert")).toContainText("10MB");
  await upload.setInputFiles({
    name: "empty.png",
    mimeType: "image/png",
    buffer: Buffer.alloc(0),
  });
  await expect(page.getByRole("alert")).toContainText("empty");
  await page.locator(".dropzone").evaluate((el) => {
    const data = new DataTransfer();
    data.items.add(
      new File(
        [
          '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40"></svg>',
        ],
        "dropped.svg",
        { type: "image/svg+xml" },
      ),
    );
    el.dispatchEvent(
      new DragEvent("drop", { bubbles: true, dataTransfer: data }),
    );
  });
  await expect(page.getByAltText("Selected ingredient label")).toBeVisible();
  await page.route("**/analyze", (route) =>
    route.fulfill({ json: { allergens: [] } }),
  );
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByRole("alert")).toContainText("incomplete analysis");
  await expect(page).toHaveURL(/scan$/);
});
