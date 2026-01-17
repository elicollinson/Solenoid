/**
 * Main Application Entry Point
 *
 * Simplified startup script that launches the API server. Used when the
 * application is run directly without the CLI wrapper. Reads port from
 * the PORT environment variable, defaulting to 8001.
 */
import { startServer } from './server/index.js';

const port = parseInt(process.env['PORT'] ?? '8001', 10);

console.log('Solenoid v2.0.0-alpha.1');
console.log('Starting services...');

await startServer(port);
