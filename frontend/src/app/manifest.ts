import type { MetadataRoute } from "next";

/** The web app's manifest: installable, with the logo's icons (brand/export-icons.mjs). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "NotFlix",
    short_name: "NotFlix",
    description: "Your anime, Netflix style.",
    start_url: "/",
    display: "standalone",
    background_color: "#141414",
    theme_color: "#141414",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
