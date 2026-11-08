import { resolve } from 'node:path'
import { defineConfig } from 'vite'

// one HTML entry per page; Vercel's cleanUrls serves /privacy for privacy.html
const page = (name: string) => resolve(import.meta.dirname, `${name}.html`)
export default defineConfig({
  build: {
    chunkSizeWarningLimit: 600,  // three.js is ~520 kB and loads lazily after first paint
    rollupOptions: { input: { main: page('index'), privacy: page('privacy'), terms: page('terms'), license: page('license'), 'open-source': page('open-source') } },
  },
})
