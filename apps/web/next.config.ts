import type { NextConfig } from "next";

const dev = process.env.NODE_ENV !== "production";
const origin = (url: string | undefined) => {
  try {
    return url ? new URL(url).origin : "";
  } catch {
    return "";
  }
};
// A Clerk publishable key is "pk_<env>_" + base64("<frontend-api-host>$").
const clerkHost = (() => {
  const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
  const host = Buffer.from(key.split("_")[2] ?? "", "base64").toString().replace(/\$$/, "");
  return /^[a-z0-9.-]+$/i.test(host) ? `https://${host}` : "";
})();
const api = origin(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
// Signed Storage URLs: hosted Supabase, or local `supabase start` whenever the API itself is local.
const localStack = dev || /^http:\/\/(localhost|127\.0\.0\.1)(:|$)/.test(api);
const storage = ["https://*.supabase.co", localStack && "http://127.0.0.1:54321 http://localhost:54321"].filter(Boolean).join(" ");

// shortcut: 'unsafe-inline' scripts because nonces force dynamic rendering (cacheComponents/PPR); move to nonces if PPR goes.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' ${dev ? "'unsafe-eval'" : ""} ${clerkHost} https://*.protect.clerk.com:* https://challenges.cloudflare.com`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: https://img.clerk.com ${storage}`,
  "font-src 'self' data:",
  `connect-src 'self' ${api} ${clerkHost} ${storage} https://clerk-telemetry.com https://*.protect.clerk.com:* ${dev ? "ws:" : ""}`,
  "worker-src 'self' blob:",
  "frame-src https://challenges.cloudflare.com",
  "media-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
]
  .map((d) => d.replace(/\s+/g, " ").trim())
  .join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=(), payment=()" },
  ...(dev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]),
];

const nextConfig: NextConfig = {
  output: "standalone", // small Node image (Dockerfile)
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
