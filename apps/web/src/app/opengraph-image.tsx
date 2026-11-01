import { ImageResponse } from "next/og";

export const alt = "AEC Studio: floor plans you can edit by saying what to change";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#14171c", color: "#f4f5f7" }}>
      <svg width="88" height="88" viewBox="0 0 24 24" fill="none">
        <path d="M3 21V3h18" stroke="#f4f5f7" strokeWidth="3" strokeLinecap="square" />
        <path d="M21 3v8" stroke="#6f9bff" strokeWidth="2" strokeLinecap="square" />
        <path d="M21 11A10 10 0 0 1 11 21" stroke="#6f9bff" strokeWidth="1.5" strokeDasharray="2 2.4" />
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ fontSize: 72, fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.05 }}>Floor plans you can edit by saying what to change.</div>
        <div style={{ fontSize: 30, color: "#a9afb9" }}>AEC Studio. The AI never moves a wall; the geometry engine does.</div>
      </div>
    </div>,
    size,
  );
}
