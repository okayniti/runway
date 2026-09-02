import type { NextConfig } from "next";

// The FastAPI backend's own URL, never exposed to the browser directly —
// all frontend calls go to same-origin /api/backend/*, which Next.js
// proxies here server-side. This keeps the backend's API contract
// completely untouched (no CORS middleware needed on it) and means the
// backend's real address is never hardcoded into client bundle code.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
