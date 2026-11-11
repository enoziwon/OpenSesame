import { useNavigate } from "react-router-dom";
import type { Allergen } from "../types/analysis";
import { allergens } from "../constants/allergens";
import { Layout, PageTitle, PrimaryButton } from "../components/Layout";
import { AllergenCard } from "../components/AllergenCard";
export default function AllergiesPage({
  selected,
  toggle,
}: {
  selected: Allergen[];
  toggle: (id: Allergen) => void;
}) {
  const navigate = useNavigate();
  return (
    <Layout step={1}>
      <main>
        <PageTitle title="My Allergies">
          Select your allergens
          <br />
          (U.S. 9 major allergens).
        </PageTitle>
        <div className="allergen-grid" role="group" aria-label="Your allergens">
          {allergens.map((a) => (
            <AllergenCard
              key={a.id}
              {...a}
              selected={selected.includes(a.id)}
              onToggle={() => toggle(a.id)}
            />
          ))}
        </div>
        <div className="bottom-actions">
          <PrimaryButton onClick={() => navigate("/scan")}>
            Next →
          </PrimaryButton>
        </div>
      </main>
    </Layout>
  );
}
