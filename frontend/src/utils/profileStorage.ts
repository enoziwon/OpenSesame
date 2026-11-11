import { allergens } from "../constants/allergens";
import type { Allergen } from "../types/analysis";
// Temporary team choice. Replace only this adapter if persistent storage is approved.
const key = "opensesame.allergies";
export const profileStorage = {
  read(): Allergen[] {
    try {
      const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? "[]");
      return Array.isArray(value)
        ? [
            ...new Set(
              value.filter((id): id is Allergen =>
                allergens.some((a) => a.id === id),
              ),
            ),
          ]
        : [];
    } catch {
      return [];
    }
  },
  write(value: Allergen[]) {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* In-memory state remains usable when storage is blocked. */
    }
  },
};
