// Rasterises the logo masters (brand/logo) into the icon sets the apps use:
//   brand/web/      favicon.ico (16/32/48), favicon.svg, PNGs for apple-touch, PWA and maskable
//   brand/desktop/  icon.png (1024, electron-builder makes the .ico/.icns from it) and 512/256
// Needs Playwright's Chromium: NODE_PATH=$(npm root -g) node brand/export-icons.mjs
// (after: npm i -g playwright && npx playwright install chromium).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

// (required, not imported: so NODE_PATH finds a global install)
const { chromium } = createRequire(import.meta.url)("playwright");

const here = path.dirname(fileURLToPath(import.meta.url));
const logo = (name) => fs.readFileSync(path.join(here, "logo", name));

const browser = await chromium.launch();
const page = await browser.newPage();

/** An SVG master as a transparent PNG of `size` × `size`. */
async function png(name, size) {
  const data = logo(name).toString("base64");
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<html><body style="margin:0;background:transparent">` +
      `<img src="data:image/svg+xml;base64,${data}" width="${size}" height="${size}" style="display:block"></body></html>`,
  );
  return page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } });
}

/** A .ico holding PNG images (supported everywhere since Windows Vista). */
function ico(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  const dir = Buffer.alloc(16 * images.length);
  let offset = 6 + dir.length;
  images.forEach(({ size, data }, i) => {
    const o = i * 16;
    dir.writeUInt8(size >= 256 ? 0 : size, o);
    dir.writeUInt8(size >= 256 ? 0 : size, o + 1);
    dir.writeUInt16LE(1, o + 4); // colour planes
    dir.writeUInt16LE(32, o + 6); // bits per pixel
    dir.writeUInt32LE(data.length, o + 8);
    dir.writeUInt32LE(offset, o + 12);
    offset += data.length;
  });
  return Buffer.concat([header, dir, ...images.map((i) => i.data)]);
}

const write = (dir, name, data) => {
  fs.mkdirSync(path.join(here, dir), { recursive: true });
  fs.writeFileSync(path.join(here, dir, name), data);
};

// Web: favicons from the small cut; touch and PWA icons from the app icon (ink tile).
const fav = [];
for (const size of [16, 32, 48]) {
  const data = await png("notflix-favicon.svg", size);
  fav.push({ size, data });
  write("web", `favicon-${size}.png`, data);
}
write("web", "favicon.ico", ico(fav));
write("web", "favicon.svg", logo("notflix-favicon.svg"));
write("web", "apple-touch-icon.png", await png("notflix-app-icon.svg", 180));
write("web", "icon-192.png", await png("notflix-app-icon.svg", 192));
write("web", "icon-512.png", await png("notflix-app-icon.svg", 512));
write("web", "maskable-512.png", await png("notflix-maskable.svg", 512));

// Desktop app: electron-builder turns icon.png (at least 512, here 1024) into .ico and .icns.
write("desktop", "icon.png", await png("notflix-app-icon.svg", 1024));
write("desktop", "icon-256.png", await png("notflix-app-icon.svg", 256));
write(
  "desktop",
  "icon.ico",
  ico(await Promise.all([16, 24, 32, 48, 64, 128, 256].map(async (size) => ({ size, data: await png("notflix-app-icon.svg", size) })))),
);

await browser.close();

// Into the apps: the web app's icons (app/ file conventions and public/), the desktop app's.
const root = path.join(here, "..");
const copy = (from, to) => fs.copyFileSync(path.join(here, from), path.join(root, to));
copy("web/favicon.ico", "frontend/src/app/favicon.ico");
copy("web/favicon.svg", "frontend/src/app/icon.svg");
copy("web/apple-touch-icon.png", "frontend/src/app/apple-icon.png");
for (const name of ["icon-192.png", "icon-512.png", "maskable-512.png"]) copy(`web/${name}`, `frontend/public/${name}`);
fs.mkdirSync(path.join(root, "desktop", "icons"), { recursive: true });
for (const name of ["icon.png", "icon.ico", "icon-256.png"]) copy(`desktop/${name}`, `desktop/icons/${name}`);
console.log("icons written to brand/web and brand/desktop, and copied into frontend/ and desktop/icons/");
