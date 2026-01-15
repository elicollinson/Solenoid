import { startServer } from './server/index.js';

const port = parseInt(process.env['PORT'] ?? '8001', 10);

console.log('Solenoid v2.0.0-alpha.1');
console.log('Starting services...');

await startServer(port);
