import { Link } from "react-router-dom";
import type { ReactNode, ButtonHTMLAttributes } from "react";
export function Layout({
  step,
  children,
}: {
  step?: number;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <header>
        <Link className="logo" to="/" aria-label="OpenSesame home">
          Open<span>Sesame</span>
          <i />
        </Link>
        <span className="language" aria-label="Language: English">
          EN
        </span>
      </header>
      {step && (
        <nav aria-label="Progress" className="steps">
          {["My Allergies", "Scan", "Results"].map((label, i) => (
            <span
              key={label}
              className={step === i + 1 ? "active" : ""}
              aria-current={step === i + 1 ? "step" : undefined}
            >
              <b className={step >= i + 1 ? "filled" : ""}>
                {step > i + 1 ? "✓" : i + 1}
              </b>
              {i < 2 ? (
                <Link to={i === 0 ? "/allergies" : "/scan"}>{label}</Link>
              ) : (
                label
              )}
            </span>
          ))}
        </nav>
      )}
      {children}
    </div>
  );
}
export function PrimaryButton({
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`primary ${className}`} {...props}>
      {children}
    </button>
  );
}
export function PageTitle({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="page-title">
      <h1>{title}</h1>
      <p>{children}</p>
    </div>
  );
}
