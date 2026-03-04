import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@components': resolve(__dirname, 'src/components'),
      '@store': resolve(__dirname, 'src/store'),
      '@hooks': resolve(__dirname, 'src/hooks'),
      '@types': resolve(__dirname, 'src/types'),
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Code splitting
    rollupOptions: {
      output: {
        manualChunks: {
          // Vendor chunk
          vendor: ['react', 'react-dom'],
          // Markdown chunk (large)
          markdown: ['react-markdown', 'remark-gfm', 'rehype-highlight'],
        },
      },
    },
    // Chunk size warning
    chunkSizeWarningLimit: 1000,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'zustand'],
  },
})
