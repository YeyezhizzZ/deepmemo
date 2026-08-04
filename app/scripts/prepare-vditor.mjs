import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(appRoot, 'node_modules/vditor/dist');
const target = resolve(appRoot, 'public/vditor/dist');

if (!existsSync(source)) {
  throw new Error(`Vditor assets not found at ${source}; run npm install first.`);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(dirname(target), { recursive: true });
cpSync(source, target, { recursive: true });

console.log(`Prepared Vditor assets at ${target}`);
