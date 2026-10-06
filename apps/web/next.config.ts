import type { NextConfig } from "next";

const API_URL = (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The browser only ever talks to this origin; /api/* is proxied to the FastAPI service.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
