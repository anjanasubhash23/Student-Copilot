import type { NextConfig } from "next";

// The browser only ever talks to this Next.js server; /api/* is proxied to FastAPI. Same origin means
// the API's HttpOnly session cookie just works, with no CORS.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  // A self-contained server for the Docker image (web/Dockerfile).
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  experimental: {
    // Generating questions with a local model can take a minute or more; the default proxy timeout is 30s.
    proxyTimeout: 300_000,
  },
};

export default config;
