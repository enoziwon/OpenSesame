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
  reason_en?: string;
  reason_ko?: string;
  basis?: string[];
  species?: string[];
  evidence_en?: string | null;
  read_as?: string | null;
  explanation_en?: string | null;
}
export interface FacilityResult {
  allergen: Allergen;
  words: string[];
  reason_en: string;
  reason_ko?: string;
}
export interface Analysis {
  ingredients_text: string;
  ingredients: Ingredient[];
  allergens: AllergenResult[];
  shared_facility?: FacilityResult[];
  warnings: string[];
  undecidable_ingredients?: string[];
  declaration_text?: string | null;
  notes?: string[];
  meta?: {
    ocr_engine?: string;
    classifier?: string;
    prompt_version?: string | null;
  };
}
