import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
  // Vitest reads this same config (docs/deviations.md Part 14, Part B) — no separate
  // vitest.config.js needed. jsdom, not the (faster) default node environment: these tests
  // render real React components and need a DOM.
  //
  // esbuild.jsx explicitly forced to the automatic runtime: without this, source files under
  // test (not just this project's own test files) throw "React is not defined" — this Vite
  // version's rolldown-based build pipeline and @vitejs/plugin-react's automatic-runtime JSX
  // transform aren't being picked up by Vitest's own (separate, esbuild-based) transform step,
  // so it silently falls back to assuming the classic runtime instead. `vite build`/`vite dev`
  // are unaffected either way — this only patches Vitest's test-time transform.
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'jsdom',
    // 15 s, not vitest's 5 s: the heaviest component tests render whole forms and take up to
    // ~3.5 s on an idle machine; with the backend suite and coverage running alongside (load
    // average 10+ on the dev box) they crossed 5 s and failed at random. A real hang still fails.
    testTimeout: 15000,
    setupFiles: './src/test/setup.js',
    globals: true,
  },
})
