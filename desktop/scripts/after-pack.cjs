// electron-builder leaves node_modules out of extraResources, but the server needs its own
// (Next.js and its dependencies). So server/ is copied into the app's resources here.

const { cpSync } = require("node:fs");
const { join } = require("node:path");

exports.default = async function afterPack(context) {
  const resources =
    context.electronPlatformName === "darwin"
      ? join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents", "Resources")
      : join(context.appOutDir, "resources");
  cpSync(join(__dirname, "..", "server"), join(resources, "server"), { recursive: true });
};
