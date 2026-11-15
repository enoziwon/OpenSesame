import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LoaderCircle, X } from "lucide-react";
import { Layout, PageTitle, PrimaryButton } from "../components/Layout";
import { analyzeImage } from "../api/analyze";
import { validateImage } from "../utils/analysis";
import type { Analysis } from "../types/analysis";
import cameraIcon from "../assets/camera.svg";
import libraryIcon from "../assets/library.svg";
export default function ScanPage({
  onResult,
}: {
  onResult: (a: Analysis) => void;
}) {
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const camera = useRef<HTMLInputElement>(null),
    gallery = useRef<HTMLInputElement>(null),
    request = useRef<AbortController | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => () => request.current?.abort(), []);
  function choose(next?: File) {
    if (!next || request.current) return;
    const problem = validateImage(next);
    setError(problem);
    if (!problem) setFile(next);
  }
  async function analyze() {
    if (!file || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const result = await analyzeImage(file, controller.signal);
      if (!controller.signal.aborted) {
        onResult(result);
        navigate("/results");
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Analysis failed. Please try again.",
        );
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setBusy(false);
      }
    }
  }
  return (
    <Layout step={2}>
      <main aria-busy={busy}>
        <PageTitle title="Scan Ingredients">
          Upload a photo of the ingredient list
          <br />
          on the Korean food label.
        </PageTitle>
        <div
          className={`dropzone ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!busy) {
              if (e.dataTransfer.files.length !== 1)
                setError("Choose one image at a time.");
              else choose(e.dataTransfer.files[0]);
            }
          }}
        >
          <div className="upload-placeholder" aria-hidden="true">
            <i />
            <b />
          </div>
          <p>Drag &amp; drop an image here</p>
          <small>or use the buttons below</small>
        </div>
        <div className="photo-actions">
          <button
            disabled={busy}
            className="take-photo"
            onClick={() => camera.current?.click()}
          >
            <img src={cameraIcon} alt="" />
            Take Photo
          </button>
          <button disabled={busy} onClick={() => gallery.current?.click()}>
            <img src={libraryIcon} alt="" />
            Upload Photo
          </button>
        </div>
        <input
          hidden
          ref={camera}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <input
          hidden
          ref={gallery}
          type="file"
          accept="image/*"
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        {file && preview && (
          <div className="preview">
            <img
              src={preview}
              alt="Selected ingredient label"
              onError={() => {
                setError(
                  "This image cannot be previewed in this browser. Try JPEG or PNG.",
                );
                setFile(undefined);
              }}
            />
            <button
              aria-label="Remove image"
              disabled={busy}
              onClick={() => {
                setFile(undefined);
                setError("");
              }}
            >
              <X size={18} />
            </button>
          </div>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {busy && (
          <p role="status" className="loading">
            <LoaderCircle className="spin" size={20} />
            Analyzing your ingredient label…
          </p>
        )}
        <div className="bottom-actions">
          <PrimaryButton disabled={!file || busy} onClick={analyze}>
            {busy ? "Analyzing…" : "Analyze →"}
          </PrimaryButton>
        </div>
      </main>
    </Layout>
  );
}
