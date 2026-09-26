import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.DARTSCORE_BACKEND ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // im Heimnetz erreichbar, damit Handy/Tablet schon während der Entwicklung testen können
    host: true,
    proxy: {
      '/api': backend,
      '/ws': { target: backend, ws: true },
    },
  },
})
