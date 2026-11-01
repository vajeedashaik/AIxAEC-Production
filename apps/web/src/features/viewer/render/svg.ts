import { LAYERS, tokenVar, type Primitive, type Pt, type Scene } from "./types";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

export const pointsAttr = (pts: readonly Pt[]) => pts.map((p) => `${p[0]},${p[1]}`).join(" ");

function primitiveToSvg(p: Primitive): string {
  const common =
    `data-element-id="${esc(p.elementId)}" data-kind="${p.kind}" fill="${tokenVar(p.fill)}" stroke="${tokenVar(p.stroke)}"` +
    (p.strokeWidth ? ` stroke-width="${p.strokeWidth}"` : "");
  switch (p.type) {
    case "polygon":
      return `<polygon ${common} points="${pointsAttr(p.points)}"/>`;
    case "line":
      return `<line ${common} x1="${p.from[0]}" y1="${p.from[1]}" x2="${p.to[0]}" y2="${p.to[1]}"/>`;
    case "path":
      return `<path ${common} d="${esc(p.d)}"/>`;
    case "text":
      return `<text ${common} x="${p.at[0]}" y="${p.at[1]}" font-size="${p.size}" text-anchor="middle">${esc(p.text)}</text>`;
  }
}

/** Byte-identical for equal scenes; text and ids are escaped. */
export function sceneToSvgString(scene: Scene): string {
  const groups = LAYERS.map((layer) => {
    const inner = scene.primitives.filter((p) => p.layer === layer).map(primitiveToSvg).join("");
    return inner && `<g data-layer="${layer}">${inner}</g>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${scene.width} ${scene.height}">${groups}</svg>`;
}
