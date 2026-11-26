// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const runtime = JSON.parse(
  readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../config/runtime.json"), "utf8"),
);
const overlay = runtime.services.overlay;
const gestures = runtime.services.gestures;
const injectedRuntime = {
  // DARK_TEST_WS_PORT solo sirve para probar la interfaz contra un puente falso en desarrollo.
  overlayWsUrl: `ws://127.0.0.1:${process.env["DARK_TEST_WS_PORT"] ?? overlay.websocketPort}`,
  overlayHttpUrl: `http://127.0.0.1:${overlay.httpPort}`,
  gesturesWsUrl: `ws://${gestures.host}:${gestures.port}`,
};

export default defineConfig({
  // The installer ships a local Windows runtime; Cloudflare's default preset
  // produces a deploy bundle that the installed Supervisor cannot launch.
  nitro: { preset: "node-server" },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    // Record package licenses for modules that actually survive into the
    // browser bundles. The installer folds this artifact into its notice set.
    build: { license: { fileName: "dark-bundle-licenses.json" } },
    define: { __DARK_RUNTIME__: JSON.stringify(injectedRuntime) },
    optimizeDeps: {
      include: [
        "use-sync-external-store",
        "use-sync-external-store/shim/with-selector",
      ],
    },
    server: {
      watch: {
        ignored: [/DarkManager/, /node_modules/, /\.git/, /venv/, /\.vs/],
      },
      // Tele → :8080/dark-bridge → Python :8765 (evita abrir 8765 en el firewall)
      proxy: {
        "/dark-bridge": {
          target: `http://127.0.0.1:${overlay.websocketPort}`,
          ws: true,
          changeOrigin: true,
          rewrite: (path: string) => {
            const stripped = path.replace(/^\/dark-bridge/, "");
            return stripped.length ? stripped : "/";
          },
        },
        "/dark-state": {
          target: `http://127.0.0.1:${overlay.httpPort}`,
          changeOrigin: true,
          rewrite: (path: string) =>
            path.replace(/^\/dark-state/, "/state") || "/state",
        },
      },
    },
  },
});
