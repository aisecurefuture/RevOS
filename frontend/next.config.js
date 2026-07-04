/** @type {import('next').NextConfig} */

// Proxy /api/* to the FastAPI backend so the browser stays same-origin.
// This keeps auth cookies first-party (no CORS/SameSite headaches) and avoids
// exposing the backend URL to the client. Override in Docker via env.
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

// Security headers applied to all frontend responses (defense in depth; the
// backend independently sets its own headers on /api responses).
//
// Content-Security-Policy is enforced in production only: it needs
// 'unsafe-inline'/'unsafe-eval' in script-src because Next's hydration bootstrap
// uses inline scripts and we don't wire per-request nonces, so its real value is
// locking down framing, base-uri, form-action, object/embed, and the set of
// origins the page may connect to or load resources from. It is disabled in dev
// so it doesn't block the HMR websocket. img-src allows https: so user avatar
// URLs render; connect-src is 'self' because the browser only ever calls the
// same-origin /api proxy.
const isProd = process.env.NODE_ENV === "production";

const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
  ...(isProd ? [{ key: "Content-Security-Policy", value: CONTENT_SECURITY_POLICY }] : []),
];

const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // small production image
  poweredByHeader: false, // don't advertise the framework
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_INTERNAL_URL}/api/:path*` },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

module.exports = nextConfig;
