// Runs electron-vite without ELECTRON_RUN_AS_NODE, which VS Code terminals set and which makes Electron act as plain Node.
import { spawn } from 'node:child_process'
delete process.env.ELECTRON_RUN_AS_NODE
spawn('npx', ['electron-vite', ...process.argv.slice(2)], { stdio: 'inherit', shell: true }).on('exit', (c) => process.exit(c ?? 0))
