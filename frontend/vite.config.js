import { readFileSync } from 'node:fs';
import { defineConfig } from 'vite';

export default defineConfig({
  publicDir: false,
  plugins: [
    {
      name: 'copy-existing-static-app-assets',
      configureServer(server) {
        server.middlewares.use((request, _response, next) => {
          if (request.url?.startsWith('/static/')) {
            request.url = request.url.replace(/^\/static\//, '/');
          }
          next();
        });
      },
      generateBundle() {
        for (const fileName of ['app.js', 'styles.css', 'logo.png']) {
          this.emitFile({
            type: 'asset',
            fileName,
            source: readFileSync(new URL(`./${fileName}`, import.meta.url))
          });
        }
      }
    }
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true
  }
});
