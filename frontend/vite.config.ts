import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Use the Docker proxy by default so dev auth uses the running database.
      '/api': process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8080',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    pool: 'threads',
    maxWorkers: 1,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
