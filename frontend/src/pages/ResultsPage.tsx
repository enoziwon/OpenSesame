import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { Layout, PageTitle, PrimaryButton } from "../components/Layout";
import { allergens, verdictLabels } from "../constants/allergens";
import { hasIncompleteAnalysis } from "../utils/analysis";
import type { Analysis, Allergen } from "../types/analysis";
import chevron from "../assets/results/chevron.svg";

const displayOrder: Allergen[] = [
  "peanut",
  "sesame",
  "milk",
  "wheat",
  "egg",
  "fish",
  "crustacean",
  "tree_nut",
  "soy",
];

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

  const incomplete = hasIncompleteAnalysis(result);
  const matches = result.allergens.filter((a) => selected.includes(a.allergen));
  const confirmed = matches.filter((a) => a.verdict === "confirmed").length;
  const review = matches.filter((a) => a.verdict !== "confirmed").length;
  const uncertain =
    incomplete ||
    !!result.undecidable_ingredients?.length ||
    result.allergens.some((a) => a.verdict === "undecidable");
  const rank = (id: Allergen) => {
    const found = result.allergens.find((a) => a.allergen === id);
    return found
      ? { confirmed: 0, inferable: 1, undecidable: 2 }[found.verdict]
      : 3;
  };
  const ordered = [...displayOrder].sort((a, b) => rank(a) - rank(b));

  return (
    <Layout step={3} className="results-shell">
      <main className="results">
        <PageTitle title="Results">
          Review your personalized results below.
        </PageTitle>
        {(result.meta?.ocr_engine === "mock" || result.meta?.classifier === "mock") && (
          <div className="mock-banner" role="alert">
            Demo analysis: sample data is being used. The uploaded photo was not analyzed; do not use these results for allergy decisions.
          </div>
        )}
        <div
          className={`result-banner ${confirmed ? "match" : ""}`}
          role="status"
        >
          <AlertTriangle size={27} aria-hidden="true" />
          <div>
            <strong>
              {confirmed
                ? "Allergen Warning"
                : uncertain || review
                  ? "Analysis needs review"
                  : "No selected allergens detected"}
            </strong>
            <p>
              {confirmed || review
                ? `${confirmed} confirmed · ${review} results need review.`
                : "Review all results and the original label."}
            </p>
          </div>
        </div>

        <section
          className="result-table"
          aria-label="Allergen results"
          tabIndex={0}
          key={JSON.stringify(result)}
        >
          {ordered.map((id) => {
            const allergen = allergens.find((a) => a.id === id)!;
            const found = result.allergens.find((a) => a.allergen === id);
            const verdict =
              found?.verdict || (incomplete ? "undecidable" : "absent");
            const expandable =
              verdict === "inferable" || verdict === "undecidable";
            const name =
              id === "tree_nut" ? "Tree nuts" : allergen.label || allergen.name;
            const evidence =
              found &&
              [found.evidence_ingredient, ...(found.other_evidence || [])]
                .filter(Boolean)
                .join(", ");
            const heading =
              verdict === "inferable"
                ? "WHY IT MAY BE PRESENT"
                : "WHY IT'S UNCLEAR";
            const identity = (
              <>
                <span className="result-identity">
                  <img
                    className="result-icon"
                    src={
                      new URL(`../assets/results/${id}.svg`, import.meta.url)
                        .href
                    }
                    alt=""
                  />
                  <span className="result-name">{name}</span>
                </span>
                <span className="result-status">
                  <span className={`badge ${verdict}`}>
                    {verdict === "absent"
                      ? "Not detected"
                      : verdictLabels[verdict]}
                  </span>
                  {expandable ? (
                    <img className="result-chevron" src={chevron} alt="" />
                  ) : (
                    <span className="result-chevron-slot" />
                  )}
                </span>
              </>
            );
            const className = `result-row ${found && selected.includes(id) ? "highlighted" : ""}`;
            return expandable ? (
              <details className={className} key={id}>
                <summary className="result-row-heading">{identity}</summary>
                <div className={`result-reason ${verdict}`}>
                  <h2>{heading}</h2>
                  <p>
                    {found?.reason_en?.trim()
                      ? found.reason_en
                      : "The reason could not be provided. Please check the original label."}
                  </p>
                  {!found?.reason_en?.trim() && evidence && (
                    <p className="evidence">Evidence: {evidence}</p>
                  )}
                </div>
              </details>
            ) : (
              <div className={className} key={id}>
                <div className="result-row-heading">{identity}</div>
              </div>
            );
          })}

          {(uncertain || review > 0) && (
            <aside className="analysis-warning">
              <strong>Results may be incomplete</strong>
              {review > 0 && <p>Your selected allergens have uncertain findings. Use caution and check the original label.</p>}
              {!!result.undecidable_ingredients?.length && (
                <p>
                  Cannot determine the source of:{" "}
                  {result.undecidable_ingredients.join(", ")}
                </p>
              )}
              {result.warnings.map((warning, i) => (
                <p key={i}>{warning}</p>
              ))}
              {result.allergens.some((a) => a.verdict === "undecidable") && (
                <p>Some allergen verdicts cannot be determined.</p>
              )}
            </aside>
          )}
          <details className="result-source">
            <summary>Original ingredient text</summary>
            <p className="original-text">
              {result.ingredients_text || "No ingredient text was returned."}
            </p>
            {result.declaration_text && (
              <p>Allergen statement: {result.declaration_text}</p>
            )}
            {result.allergens.map((a) => (
              <div key={a.allergen} className="result-source-evidence">
                <strong>
                  {allergens.find((item) => item.id === a.allergen)?.name}
                </strong>
                <p>
                  Evidence:{" "}
                  {[a.evidence_ingredient, ...(a.other_evidence || [])]
                    .filter(Boolean)
                    .join(", ")}
                </p>
              </div>
            ))}
            {result.notes?.map((note, i) => (
              <p key={i}>{note}</p>
            ))}
            <p>
              Only the U.S. 9 major allergens are checked; other allergies are
              outside the scope of this analysis.
            </p>
          </details>
        </section>

        <p className="safety-note">
          Not detected ≠ allergen-free. Check the original label.
        </p>
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
