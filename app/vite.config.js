import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Set VITE_API_PROXY in app/.env.local e.g. http://127.0.0.1:8001 if your API is not on 8006
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY || 'http://127.0.0.1:8006'

  return {
  plugins: [react()],
  server: {
    proxy: {
      // Proxy /api/* → FastAPI backend (Stats Agent)
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      // Proxy /fpl-api/* → https://fantasy.premierleague.com/api/*
      // This bypasses the browser CORS block on the FPL API.
      '/fpl-api': {
        target: 'https://fantasy.premierleague.com',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/fpl-api/, '/api'),
        configure: proxy => {
          proxy.on('proxyReq', proxyReq => {
            // Spoof a browser User-Agent so FPL doesn't reject the request
            proxyReq.setHeader(
              'User-Agent',
              'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            proxyReq.setHeader('Accept', 'application/json, text/plain, */*')
            proxyReq.setHeader('Accept-Language', 'en-GB,en;q=0.9')
            proxyReq.setHeader('Referer', 'https://fantasy.premierleague.com/')
          })
        },
      },
    },
  },
  }
})
