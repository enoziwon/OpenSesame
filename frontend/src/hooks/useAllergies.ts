import { useState } from "react";
import { profileStorage } from "../utils/profileStorage";
import type { Allergen } from "../types/analysis";
export function useAllergies() {
  const [selected, setSelected] = useState(profileStorage.read);
  return {
    selected,
    clear() {
      profileStorage.clear();
      setSelected([]);
    },
    toggle(id: Allergen) {
      setSelected((old) => {
        const next = old.includes(id)
          ? old.filter((a) => a !== id)
          : [...old, id];
        profileStorage.write(next);
        return next;
      });
    },
  };
}
