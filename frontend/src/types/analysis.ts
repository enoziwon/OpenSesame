export type Allergen =
  | "milk"
  | "egg"
  | "fish"
  | "crustacean"
  | "tree_nut"
  | "peanut"
  | "wheat"
  | "soy"
  | "sesame";
export type Verdict = "confirmed" | "inferable" | "undecidable";
export interface Ingredient {
  name: string;
  children: Ingredient[];
}
export interface AllergenResult {
  allergen: Allergen;
  verdict: Verdict;
  evidence_ingredient: string;
  other_evidence?: string[];
}
export interface Analysis {
  ingredients_text: string;
  ingredients: Ingredient[];
  allergens: AllergenResult[];
  warnings: string[];
  undecidable_ingredients?: string[];
  meta?: {
    ocr_engine?: string;
    classifier?: string;
    prompt_version?: string | null;
  };
}
