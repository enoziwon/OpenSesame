import { useNavigate } from "react-router-dom";
import type { Allergen } from "../types/analysis";
import { allergens } from "../constants/allergens";
import { Layout, PageTitle, PrimaryButton } from "../components/Layout";
import { AllergenCard } from "../components/AllergenCard";
export default function AllergiesPage({
  selected,
  toggle,
  clear,
}: {
  selected: Allergen[];
  toggle: (id: Allergen) => void;
  clear: () => void;
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
        <p className="safety-note">
          Your allergy selections are saved only in this browser on this device
          and remain after you close it. They are not sent to the server.
        </p>
        <div className="bottom-actions">
          <button className="secondary" onClick={clear}>
            Clear My Information
          </button>
          <PrimaryButton onClick={() => navigate("/scan")}>
            Next →
          </PrimaryButton>
        </div>
      </main>
    </Layout>
  );
}
