export function LabelIllustration() {
  return (
    <div className="illustration" aria-hidden="true">
      <div className="package">
        <div className="package-top" />
        <div className="cream-label">
          {[0, 1, 2, 3].map((i) => (
            <i key={i} style={{ top: 23 + i * 21, width: i % 2 ? 62 : 72 }} />
          ))}
        </div>
      </div>
      <div className="ocr-panel">
        {[0, 1, 2, 3].map((i) => (
          <i key={i} style={{ top: 23 + i * 19, width: i % 2 ? 57 : 75 }} />
        ))}
      </div>
      {["tl", "tr", "bl", "br"].map((c) => (
        <b className={`corner ${c}`} key={c} />
      ))}
      <em className="spark s1" />
      <em className="spark s2" />
      <em className="spark s3" />
    </div>
  );
}
