/** 48213 -> "47.1 KB". Binary units, matching the 25 MB (26 214 400 bytes) upload limit. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Exact dates, not "3 days ago": this is a tool people cross-check against drawings. */
export const formatDate = (iso: string) => DATE.format(new Date(iso));
export const formatDateTime = (iso: string) => DATE_TIME.format(new Date(iso));

/** 1240 -> "1.2 s", 340 -> "340 ms". */
export const formatDuration = (ms: number) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);

/** "image/png" -> "PNG". */
export const fileKind = (contentType: string) => (contentType.split("/")[1] ?? contentType).replace("jpeg", "jpg").toUpperCase();
