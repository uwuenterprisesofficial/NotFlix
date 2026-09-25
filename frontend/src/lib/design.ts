/** UI designs: CSS-variable themes (see globals.css), chosen in Settings and kept in a cookie
 * so the server renders the right one. */
export const DESIGNS = ["standard", "communism", "miku"] as const;
export type Design = (typeof DESIGNS)[number];
export const DESIGN_COOKIE = "notflix_design";

export function isDesign(value: unknown): value is Design {
  return DESIGNS.includes(value as Design);
}

export function saveDesign(design: Design): void {
  document.cookie = `${DESIGN_COOKIE}=${design}; path=/; max-age=${60 * 60 * 24 * 365 * 2}; samesite=lax`;
  document.documentElement.dataset.design = design;
}
