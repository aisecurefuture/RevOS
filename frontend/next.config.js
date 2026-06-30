/** @type {import('next').NextConfig} */

// Proxy /api/* to the FastAPI backend so the browser stays same-origin.
// This keeps auth cookies first-party (no CORS/SameSite headaches) and avoids
// exposing the backend URL to the client. Override in Docker via env.
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

// Security headers applied to all frontend responses (defense in depth; the
// backend independently sets its own headers on /api responses). A strict CSP
// with nonces is deferred — Next's hydration uses inline scripts — but the
// framing/sniffing/referrer/permissions baseline is safe to enforce now.
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
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
