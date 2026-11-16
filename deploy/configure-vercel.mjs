import { writeFileSync } from 'node:fs';

const input = process.argv[2];
if (!input) throw new Error('Usage: node deploy/configure-vercel.mjs https://YOUR-BACKEND.onrender.com');
const backend = new URL(input);
if (backend.protocol !== 'https:' || backend.username || backend.password || backend.search || backend.hash || backend.pathname !== '/') {
  throw new Error('Provide the HTTPS backend origin without a path, credentials, or query.');
}
const config = {
  framework: 'vite',
  buildCommand: 'npm run build',
  outputDirectory: 'dist',
  rewrites: [
    { source: '/api/:path*', destination: `${backend.origin}/api/:path*` },
    { source: '/(.*)', destination: '/index.html' },
  ],
};
writeFileSync(new URL('../frontend/vercel.json', import.meta.url), JSON.stringify(config, null, 2) + '\n');
console.log(`Configured frontend/vercel.json for ${backend.origin}`);
