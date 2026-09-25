/**
 * Image hosts next/image may load from (next.config.ts allows exactly these). An image from any
 * other host would make next/image throw and break the page, so it's dropped instead and the
 * placeholder (title, initial) shows.
 */
export const IMAGE_HOSTS = [
  "cdn.myanimelist.net", // MAL posters and avatars (Jikan uses it too)
  "s4.anilist.co", // AniList avatars and covers
];

export function allowedImage(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const { protocol, hostname } = new URL(url);
    return protocol === "https:" && IMAGE_HOSTS.includes(hostname) ? url : null;
  } catch {
    return null;
  }
}
