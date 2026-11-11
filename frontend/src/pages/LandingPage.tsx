import { useNavigate } from "react-router-dom";
import { Layout, PrimaryButton } from "../components/Layout";
import { LabelIllustration } from "../components/LabelIllustration";
export default function LandingPage() {
  const navigate = useNavigate();
  return (
    <Layout>
      <main className="landing">
        <h1>
          Check Korean Food
          <br />
          <span>for Your Allergies</span>
        </h1>
        <p>
          Scan a Korean ingredient label,
          <br />
          <span>and see if it contains any of your allergens</span>
          <br />
          <small>(U.S. 9 major allergens).</small>
        </p>
        <LabelIllustration />
        <div className="bottom-actions">
          <PrimaryButton onClick={() => navigate("/allergies")}>
            Get Started →
          </PrimaryButton>
        </div>
      </main>
    </Layout>
  );
}
