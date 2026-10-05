// Preloaded (node -r) into services that listen on every network interface (Anivexa's
// server.listen(PORT)): makes them listen on 127.0.0.1 only, so nothing outside this PC
// reaches them.
const net = require("node:net");

const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function (...args) {
  if (typeof args[0] === "number" && typeof args[1] !== "string") {
    args.splice(1, 0, "127.0.0.1");
  } else if (args[0] && typeof args[0] === "object" && !args[0].host && !args[0].path) {
    args[0] = { ...args[0], host: "127.0.0.1" };
  }
  return listen.apply(this, args);
};
