import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
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
})
