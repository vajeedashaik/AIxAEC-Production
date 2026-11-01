import { round2 } from "./geometry";

// Every metric value is derived from mm_per_pixel and is null without it: px are never presented as mm.
export type MmPerPixel = number | null | undefined;
const scaled = (mpp: MmPerPixel): mpp is number => typeof mpp === "number" && Number.isFinite(mpp) && mpp > 0;

export const pxToMm = (px: number, mpp: MmPerPixel) => (scaled(mpp) ? px * mpp : null);

export const formatPx = (px: number) => `${round2(px)} px`;
export const formatPx2 = (px2: number) => `${round2(px2)} px²`;

export function formatMm(px: number, mpp: MmPerPixel): string | null {
  const mm = pxToMm(px, mpp);
  return mm === null ? null : `${round2(mm)} mm`;
}

export function formatM2(px2: number, mpp: MmPerPixel): string | null {
  if (!scaled(mpp)) return null;
  return `${round2(px2 * (mpp / 1000) ** 2)} m²`;
}

/** Best available length: metric when calibrated, px otherwise. */
export const formatLength = (px: number, mpp: MmPerPixel) => formatMm(px, mpp) ?? formatPx(px);
export const formatArea = (px2: number, mpp: MmPerPixel) => formatM2(px2, mpp) ?? formatPx2(px2);

const STEPS = [1, 2, 5];

/** Largest 1/2/5 × 10^n not above `value`. */
export function niceFloor(value: number): number {
  if (!(value > 0)) return 0;
  const pow = 10 ** Math.floor(Math.log10(value));
  return STEPS.findLast((s) => s * pow <= value * (1 + 1e-9))! * pow;
}

/** Scale-bar segment for a zoom level: its on-screen width and a label in the units we can honestly claim. */
export function scaleBar(k: number, mpp: MmPerPixel, targetScreenPx = 96): { widthPx: number; label: string } {
  const modelPx = targetScreenPx / k;
  if (scaled(mpp)) {
    const mm = niceFloor(modelPx * mpp);
    return { widthPx: (mm / mpp) * k, label: mm >= 1000 ? `${round2(mm / 1000)} m` : `${round2(mm)} mm` };
  }
  const px = niceFloor(modelPx);
  return { widthPx: px * k, label: `${round2(px)} px` };
}
