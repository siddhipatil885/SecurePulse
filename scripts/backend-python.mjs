import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const local = path.join(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.SECUREPULSE_PYTHON || (existsSync(local) ? local : process.platform === 'win32' ? 'python' : 'python3');
const child = spawn(python, process.argv.slice(2), { cwd: root, stdio: 'inherit', env: process.env });
child.on('error', () => { console.error('Python could not start. Install backend requirements and set SECUREPULSE_PYTHON if needed.'); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
