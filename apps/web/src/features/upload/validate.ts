export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
export const ACCEPT = ".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf";

const EXTENSIONS = /\.(png|jpe?g|pdf)$/i;
const TYPES = new Set(["image/png", "image/jpeg", "application/pdf"]);

/** Client pre-check, so a bad file fails instantly. The API re-validates: this is convenience, not a boundary. */
export function fileProblem(file: Pick<File, "name" | "size" | "type">): string | null {
  // Some OS/browser pairs report no MIME type, so fall back to the extension in that case only.
  if (file.type ? !TYPES.has(file.type) : !EXTENSIONS.test(file.name)) return "This isn't a PNG, JPG or PDF.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "This file is larger than 25 MB.";
  return null;
}
