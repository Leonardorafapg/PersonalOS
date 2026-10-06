import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output is for the Docker/Railway deployment; Vercel builds its own output.
  output: process.env.VERCEL ? undefined : "standalone",
  poweredByHeader: false,
  // /api/* is proxied to the FastAPI service by src/app/api/[...path]/route.ts (API_URL read at runtime).
};

export default nextConfig;
