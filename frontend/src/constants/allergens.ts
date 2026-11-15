import type { Allergen } from "../types/analysis";
export const allergens: { id: Allergen; name: string; label?: string }[] = [
  { id: "milk", name: "Milk" },
  { id: "egg", name: "Egg" },
  { id: "fish", name: "Fish" },
  { id: "crustacean", name: "Crustacean Shellfish", label: "Shellfish" },
  { id: "tree_nut", name: "Tree Nuts" },
  { id: "peanut", name: "Peanuts" },
  { id: "wheat", name: "Wheat" },
  { id: "soy", name: "Soy" },
  { id: "sesame", name: "Sesame" },
];
export const verdictLabels = {
  confirmed: "Confirmed",
  inferable: "Likely",
  undecidable: "Cannot determine",
};
