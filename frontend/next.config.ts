import type { NextConfig } from "next";
import { IMAGE_HOSTS } from "./src/lib/images";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: IMAGE_HOSTS.map((host) => new URL(`https://${host}/**`)),
    // The desktop app's server runs on the user's PC: images load straight from their CDNs
    // instead of being resized there (which needs sharp, a native module).
    unoptimized: process.env.NOTFLIX_DESKTOP_BUILD === "1",
  },
  // /api/* goes to the FastAPI backend: see src/proxy.ts.
};

export default nextConfig;
