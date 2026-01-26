/**
 * Global Test Setup
 *
 * Configures the test environment with custom matchers and global mocks.
 */
import { beforeAll, afterAll, spyOn } from 'bun:test';

// Mock crypto.randomUUID for deterministic IDs in tests
let uuidCounter = 0;
beforeAll(() => {
  spyOn(crypto, 'randomUUID').mockImplementation(() => {
    return `test-uuid-${++uuidCounter}` as `${string}-${string}-${string}-${string}-${string}`;
  });
});

afterAll(() => {
  uuidCounter = 0;
});

// Suppress console.log in tests unless DEBUG is set
if (!process.env.DEBUG) {
  spyOn(console, 'log').mockImplementation(() => {});
  spyOn(console, 'debug').mockImplementation(() => {});
}

// Reset UUID counter between test files
beforeAll(() => {
  uuidCounter = 0;
});
