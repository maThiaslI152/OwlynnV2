import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import pkg from './package.json'

// Browser-only daily use: OWLYNN_BROWSER=1 skips Electron plugins (plain Node
// cannot import BrowserWindow from 'electron' — npm run dev would crash).
const browserOnly = process.env.OWLYNN_BROWSER === '1'

// https://vite.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  plugins: [
    react(),
    ...(browserOnly
      ? []
      : [
          electron([
            {
              entry: 'electron/main.ts',
            },
            {
              entry: 'electron/preload.ts',
              onstart(options) {
                options.reload()
              },
            },
          ]),
          renderer(),
        ]),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/vendor': 'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
