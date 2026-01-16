const esbuild = require("esbuild");
const path = require("path");

const production = process.argv.includes("--production");
const watch = process.argv.includes("--watch");

/**
 * @type {import('esbuild').Plugin}
 */
const esbuildProblemMatcherPlugin = {
  name: "esbuild-problem-matcher",

  setup(build) {
    build.onStart(() => {
      console.log("[watch] build started");
    });
    build.onEnd((result) => {
      result.errors.forEach(({ text, location }) => {
        console.error(`✘ [ERROR] ${text}`);
        console.error(`    ${location.file}:${location.line}:${location.column}:`);
      });
      console.log("[watch] build finished");
    });
  },
};

async function main() {
  const ctx = await esbuild.context({
    entryPoints: ["src/extension.ts"],
    bundle: true,
    format: "cjs",
    minify: production,
    sourcemap: !production,
    sourcesContent: false,
    platform: "node",
    outfile: "dist/extension.js",
    external: ["vscode"],
    logLevel: "info",
    loader: {
      ".ts": "ts",
    },
    alias: {
      "@moonshot-ai/kimi-agent-sdk": path.resolve(__dirname, "../agent_sdk/index.ts"),
      "@moonshot-ai/kimi-agent-sdk/errors": path.resolve(__dirname, "../agent_sdk/errors.ts"),
      "@moonshot-ai/kimi-agent-sdk/schema": path.resolve(__dirname, "../agent_sdk/schema.ts"),
      "@moonshot-ai/kimi-agent-sdk/utils": path.resolve(__dirname, "../agent_sdk/utils.ts"),
    },
    plugins: [
      esbuildProblemMatcherPlugin,
      {
        name: "watch-build",
        setup(build) {
          build.onEnd((result) => {
            console.log("[watch] build finished");
          });
        },
      },
    ],
  });

  if (watch) {
    await ctx.watch();
    console.log("[watch] watching...");
  } else {
    await ctx.rebuild();
    await ctx.dispose();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
