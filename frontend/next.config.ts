import type { NextConfig } from "next";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Lean production runtime for Docker: only traced files + a minimal
  // server.js, no full node_modules copy. See frontend/Dockerfile.
  output: "standalone",

  // Proxies browser requests for /api/* to the backend container on the
  // same origin as the site. This keeps one public origin (the frontend)
  // and avoids exposing the API container directly or configuring CORS —
  // the server-rendered pages already call the API directly server-side
  // (see src/lib/api.ts); this rewrite is for future client-side calls
  // (auth, booking) that run in the browser.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
