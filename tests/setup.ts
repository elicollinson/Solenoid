/**
 * Global Test Setup
 *
 * Configures the test environment with custom matchers and global mocks.
 */
import { beforeAll, afterAll, vi } from 'vitest';

// Import custom matchers (will be created later)
// import '../src/ui/testing/matchers.js';

// Mock crypto.randomUUID for deterministic IDs in tests
let uuidCounter = 0;
beforeAll(() => {
  vi.spyOn(crypto, 'randomUUID').mockImplementation(() => {
    return `test-uuid-${++uuidCounter}` as `${string}-${string}-${string}-${string}-${string}`;
  });
});

afterAll(() => {
  vi.restoreAllMocks();
  uuidCounter = 0;
});

// Increase timeout for React reconciliation
vi.setConfig({ testTimeout: 10000 });

// Suppress console.log in tests unless DEBUG is set
if (!process.env.DEBUG) {
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'debug').mockImplementation(() => {});
}

// Reset UUID counter between test files
beforeAll(() => {
  uuidCounter = 0;
});
