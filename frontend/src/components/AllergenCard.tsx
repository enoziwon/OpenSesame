import type { Allergen } from "../types/analysis";
export function AllergenIcon({
  id,
  result = false,
}: {
  id: Allergen;
  result?: boolean;
}) {
  return (
    <img
      className="allergen-icon"
      src={
        new URL(
          `../assets/${result && ["peanut", "sesame", "milk", "egg", "wheat"].includes(id) ? "result-" : ""}${id}.svg`,
          import.meta.url,
        ).href
      }
      alt=""
    />
  );
}
export function AllergenCard({
  id,
  name,
  label,
  selected,
  onToggle,
}: {
  id: Allergen;
  name: string;
  label?: string;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <label className={`allergen-card ${selected ? "selected" : ""}`}>
      <AllergenIcon id={id} />
      <span>{label || name}</span>
      <input
        type="checkbox"
        aria-label={name}
        checked={selected}
        onChange={onToggle}
      />
    </label>
  );
}
