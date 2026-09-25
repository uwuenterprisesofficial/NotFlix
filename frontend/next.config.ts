import type { NextConfig } from "next";
import { IMAGE_HOSTS } from "./src/lib/images";

const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: IMAGE_HOSTS.map((host) => new URL(`https://${host}/**`)),
  },
  // The browser only ever talks to this origin; /api/* is proxied to FastAPI so the session
  // cookie is first-party and the MAL OAuth callback can live at /api/auth/callback.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
