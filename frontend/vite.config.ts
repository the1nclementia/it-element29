import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    pool: 'threads',
    maxWorkers: 1,
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
