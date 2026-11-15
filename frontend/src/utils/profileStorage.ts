import { allergens } from "../constants/allergens";
import type { Allergen } from "../types/analysis";
// The profile stays in this browser and is never part of an API request.
const key = "opensesame.allergies";
export const profileStorage = {
  clear() {
    try {
      localStorage.removeItem(key);
    } catch {
      /* In-memory state can still be cleared when storage is blocked. */
    }
  },
  read(): Allergen[] {
    try {
      const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
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
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* In-memory state remains usable when storage is blocked. */
    }
  },
};
