// electron-builder leaves node_modules out of extraResources, but the app's own web server
// needs its own (Next.js and its dependencies), and so do the built-in server's parts. So both
// are copied into the app's resources here: server/ and, when it was built, build/stack/.

const { cpSync, existsSync } = require("node:fs");
const { join } = require("node:path");

exports.default = async function afterPack(context) {
  const resources =
    context.electronPlatformName === "darwin"
      ? join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents", "Resources")
      : join(context.appOutDir, "resources");
  const desktop = join(__dirname, "..");
  // verbatimSymlinks: PostgreSQL's libraries link to each other relatively.
  const options = { recursive: true, verbatimSymlinks: true };
  cpSync(join(desktop, "server"), join(resources, "server"), options);
  if (existsSync(join(desktop, "build", "stack", "manifest.json"))) {
    cpSync(join(desktop, "build", "stack"), join(resources, "stack"), options);
  }
};
