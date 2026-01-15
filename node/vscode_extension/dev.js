const { spawn } = require("child_process");

console.log("🚀 Starting development environment...\n");

const extensionWatch = spawn("node", ["esbuild.js", "--watch"], {
  cwd: __dirname,
  stdio: "inherit",
  shell: true,
});

const webviewWatch = spawn("npm", ["run", "build", "--", "--watch"], {
  cwd: __dirname + "/webview-ui",
  stdio: "inherit",
  shell: true,
});

function shutdown() {
  console.log("\n🛑 Shutting down...\n");
  extensionWatch.kill("SIGINT");
  webviewWatch.kill("SIGINT");
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("exit", shutdown);

extensionWatch.on("error", (err) => {
  console.error("Extension build error:", err);
  shutdown();
});

webviewWatch.on("error", (err) => {
  console.error("Webview build error:", err);
  shutdown();
});

console.log("✅ Watching extension and webview for changes");
console.log("   Press F5 in VSCode to test\n");
