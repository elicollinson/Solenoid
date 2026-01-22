import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/ui/testing/**', // Don't test the test utilities themselves
      ],
      thresholds: {
        // Start with minimal thresholds, increase as coverage improves
        lines: 30,
        functions: 30,
        branches: 30,
        statements: 30,
      },
    },
    testTimeout: 30000,
    hookTimeout: 10000,
    setupFiles: ['tests/setup.ts'],
    // Retry flaky tests in CI
    retry: process.env.CI ? 2 : 0,
  },
});
