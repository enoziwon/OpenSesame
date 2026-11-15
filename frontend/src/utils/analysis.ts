import type { Analysis, AllergenResult } from "../types/analysis";
import { allergens } from "../constants/allergens";
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((s) => typeof s === "string");
export function normalizeAnalysis(value: unknown): Analysis {
  if (!value || typeof value !== "object")
    throw new Error("The server returned an invalid analysis.");
  const v = value as Record<string, unknown>;
  if (
    typeof v.ingredients_text !== "string" ||
    !Array.isArray(v.ingredients) ||
    !Array.isArray(v.allergens) ||
    !strings(v.warnings)
  )
    throw new Error(
      "The server returned an incomplete analysis. Please retry.",
    );
  for (const item of v.allergens) {
    const a = item as AllergenResult;
    if (
      !a ||
      !allergens.some((x) => x.id === a.allergen) ||
      !["confirmed", "inferable", "undecidable"].includes(a.verdict) ||
      typeof a.evidence_ingredient !== "string"
    )
      throw new Error("The server returned an unsupported allergen result.");
  }
  const result = {
    ...v,
    allergens: v.allergens.map((a) => ({
      ...a,
      other_evidence: strings(a.other_evidence) ? a.other_evidence : [],
    })),
    undecidable_ingredients: strings(v.undecidable_ingredients)
      ? v.undecidable_ingredients
      : [],
    meta: v.meta && typeof v.meta === "object" ? v.meta : undefined,
  } as Analysis;
  if (!result.ingredients_text.trim() || !result.ingredients.length)
    result.warnings = [
      ...result.warnings,
      "The ingredient label could not be fully read. Results may be incomplete.",
    ];
  return result;
}
export function isMock(a: Analysis) {
  return a.meta?.ocr_engine === "mock" || a.meta?.classifier === "mock";
}
// A missing match is not a negative finding when reading/classification failed.
export function hasIncompleteAnalysis(a: Analysis) {
  return (
    !!a.warnings.length || !a.ingredients_text.trim() || !a.ingredients.length
  );
}
export function validateImage(file: File) {
  if (!file.type.startsWith("image/")) return "Choose an image file.";
  if (!file.size) return "This image is empty.";
  if (file.size > 10 * 1024 * 1024)
    return "Choose an image no larger than 10MB.";
  return "";
}
