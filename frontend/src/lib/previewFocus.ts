/** Previews other than the featured show's (the hover cards) that are playing: the featured
 * show's preview pauses while there are any. */

export const OTHER_PREVIEW_EVENT = "notflix:other-preview";

let playing = 0;

/** A hover card's preview started (true) or stopped (false) playing. */
export function otherPreviewPlaying(active: boolean): void {
  playing = Math.max(0, playing + (active ? 1 : -1));
  window.dispatchEvent(new Event(OTHER_PREVIEW_EVENT));
}

export function otherPreviewsPlaying(): boolean {
  return playing > 0;
}
