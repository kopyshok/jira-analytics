import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 700,
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
  },
})
