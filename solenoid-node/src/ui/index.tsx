import { render } from 'ink';
import { App } from './app.js';

const serverUrl = process.env['SOLENOID_SERVER_URL'] ?? 'http://localhost:8001';

const instance = render(<App serverUrl={serverUrl} />);

await instance.waitUntilExit();
