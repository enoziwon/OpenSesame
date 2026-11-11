import { normalizeAnalysis } from "../utils/analysis";
export async function analyzeImage(file: File, signal: AbortSignal) {
  const body = new FormData();
  body.append("file", file);
  let response: Response;
  try {
    response = await fetch(
      `${(import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "")}/analyze`,
      { method: "POST", body, signal },
    );
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error(
      "Unable to reach the analysis server. Check your connection and try again.",
    );
  }
  if (!response.ok)
    throw new Error(
      response.status === 413
        ? "The server rejected this image: maximum size is 10MB."
        : `Analysis failed (${response.status}). Please try again.`,
    );
  return normalizeAnalysis(await response.json());
}
