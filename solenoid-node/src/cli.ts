#!/usr/bin/env node
import { program } from 'commander';
import { startServer } from './server/index.js';

program
  .name('solenoid')
  .description('Multi-agent AI assistant with local LLM inference')
  .version('2.0.0-alpha.1');

program
  .command('serve')
  .description('Start the Solenoid API server')
  .option('-p, --port <number>', 'Port to listen on', '8001')
  .action(async (options) => {
    const port = parseInt(options.port, 10);
    await startServer(port);
  });

program
  .command('ui')
  .description('Start the terminal UI (requires server running)')
  .option('-s, --server <url>', 'Server URL', 'http://localhost:8001')
  .action(async (options) => {
    process.env['SOLENOID_SERVER_URL'] = options.server;
    await import('./ui/index.js');
  });

program
  .command('start', { isDefault: true })
  .description('Start both server and UI')
  .option('-p, --port <number>', 'Server port', '8001')
  .action(async (options) => {
    const port = parseInt(options.port, 10);

    await startServer(port);

    process.env['SOLENOID_SERVER_URL'] = `http://localhost:${port}`;
    await import('./ui/index.js');
  });

program.parse();
