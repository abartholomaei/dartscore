import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.DARTSCORE_BACKEND ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // reachable on the home network so phones/tablets can test during development
    host: true,
    proxy: {
      '/api': backend,
      '/ws': { target: backend, ws: true },
    },
  },
})
