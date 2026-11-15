import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { Layout, PageTitle, PrimaryButton } from "../components/Layout";
import { AllergenIcon } from "../components/AllergenCard";
import { allergens, verdictLabels } from "../constants/allergens";
import { hasIncompleteAnalysis, isMock } from "../utils/analysis";
import type { Analysis, Allergen } from "../types/analysis";
export default function ResultsPage({
  result,
  selected,
}: {
  result: Analysis | null;
  selected: Allergen[];
}) {
  const navigate = useNavigate();
  if (!result)
    return (
      <Layout step={3}>
        <main>
          <PageTitle title="Results">
            No analysis is available. Scan an ingredient label to begin.
          </PageTitle>
          <Link className="primary" to="/scan">
            Scan Ingredients →
          </Link>
        </main>
      </Layout>
    );
  const matches = result.allergens.filter((a) => selected.includes(a.allergen));
  const incomplete = hasIncompleteAnalysis(result);
  const confirmedMatches = matches.filter((a) => a.verdict === "confirmed");
  const uncertainMatches = matches.some((a) => a.verdict !== "confirmed");
  const uncertain =
    !!result.undecidable_ingredients?.length ||
    result.allergens.some((a) => a.verdict === "undecidable") ||
    !!result.warnings.length;
  return (
    <Layout step={3}>
      <main className="results">
        <PageTitle title="Results">Allergen check for this product.</PageTitle>
        {isMock(result) && (
          <p className="mock-banner" role="status">
            Demo analysis — backend mock mode. Results are fixed and do not
            describe your photo.
          </p>
        )}
        <div
          className={`result-banner ${matches.length ? "match" : ""}`}
          role="status"
        >
          <AlertTriangle size={26} />
          <div>
            <strong>
              {confirmedMatches.length
                ? "Allergen Match Detected"
                : uncertain || uncertainMatches
                  ? "Analysis needs review"
                  : "No selected allergens detected"}
            </strong>
            <p>
              {matches.length
                ? `${matches.length} of your selected allergens have a result. Review the verdicts below.`
                : "Review all results and the original label before deciding."}
            </p>
            {uncertainMatches && (
              <p>
                Your selected allergens have uncertain findings. Use caution and
                check the original label.
              </p>
            )}
          </div>
        </div>
        <div className="result-table">
          {allergens.map((a) => {
            const found = result.allergens.find((r) => r.allergen === a.id);
            const highlighted = !!found && selected.includes(a.id);
            return (
              <div
                key={a.id}
                className={`result-row ${highlighted ? "highlighted" : ""}`}
              >
                <AllergenIcon id={a.id} result />
                <span className="result-name">
                  {a.label || a.name}
                  {highlighted && <small>Your allergen</small>}
                </span>
                <span
                  className={`badge ${found?.verdict || (incomplete ? "undecidable" : "absent")}`}
                >
                  {found
                    ? verdictLabels[found.verdict]
                    : incomplete
                      ? "Cannot determine"
                      : "Not detected"}
                </span>
                {found && (
                  <p className="evidence">
                    Evidence:{" "}
                    {[
                      found.evidence_ingredient,
                      ...(found.other_evidence || []),
                    ]
                      .filter(Boolean)
                      .join(", ")}
                  </p>
                )}
              </div>
            );
          })}
        </div>
        {uncertain && (
          <aside className="analysis-warning">
            <strong>Results may be incomplete</strong>
            {!!result.undecidable_ingredients?.length && (
              <p>
                Cannot determine the source of:{" "}
                {result.undecidable_ingredients.join(", ")}
              </p>
            )}
            {result.warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
            {result.allergens.some((a) => a.verdict === "undecidable") && (
              <p>Some allergen verdicts cannot be determined.</p>
            )}
          </aside>
        )}
        <p className="safety-note">
          Not detected does not mean safe. Always check the original label. Only
          the U.S. 9 major allergens are checked; other allergies are outside
          the scope of this analysis.
        </p>
        <details>
          <summary>Original ingredient text</summary>
          <p className="original-text">
            {result.ingredients_text || "No ingredient text was returned."}
          </p>
        </details>
        <div className="bottom-actions result-actions">
          <button className="secondary" onClick={() => navigate("/scan")}>
            Scan Another
          </button>
          <PrimaryButton
            aria-label="Edit My Allergies"
            onClick={() => navigate("/allergies")}
          >
            Edit Allergies
          </PrimaryButton>
        </div>
      </main>
    </Layout>
  );
}
