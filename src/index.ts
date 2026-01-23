/**
 * Main Application Entry Point
 *
 * Simplified startup script that launches the terminal UI with integrated
 * agent system. Used when the application is run directly.
 */
console.log('Solenoid v2.0.0-alpha.1');

await import('./ui/index.js');
