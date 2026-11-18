import { normalizeAnalysis } from "../utils/analysis";
async function analyze(path: string, body: BodyInit, signal: AbortSignal, headers?: HeadersInit) {
  let response: Response;
  try {
    response = await fetch(
      `${(import.meta.env.VITE_API_BASE_URL || "http://localhost:8001").replace(/\/$/, "")}${path}`,
      { method: "POST", body, signal, headers },
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
        : response.status === 503
          ? "Photo analysis is not configured. Try entering the ingredient text instead."
        : `Analysis failed (${response.status}). Please try again.`,
    );
  const result = normalizeAnalysis(await response.json());
  return result;
}

export function analyzeImage(file: File, signal: AbortSignal) {
  const body = new FormData();
  body.append("file", file);
  return analyze("/analyze", body, signal);
}

export function analyzeText(text: string, signal: AbortSignal) {
  return analyze("/analyze-text", JSON.stringify({ text }), signal, {
    "Content-Type": "application/json",
  });
}
