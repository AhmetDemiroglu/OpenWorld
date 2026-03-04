import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setupTests.js',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'tests/',
        '**/*.d.ts',
        '**/*.test.{ts,tsx}',
        '**/types/**',
      ],
    },
  },
  resolve: {
    alias: {
      '@': '/src',
      '@components': '/src/components',
      '@store': '/src/store',
      '@hooks': '/src/hooks',
      '@types': '/src/types',
    },
  },
});
