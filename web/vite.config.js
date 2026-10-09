import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

// Su GitHub Pages il sito vive in /<nome-repository>/ : VITE_BASE viene impostata dal workflow.
const base = process.env.VITE_BASE || '/';

export default defineConfig({
  base,
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Il Mio Giornale',
        short_name: 'Giornale',
        description: 'Il tuo quotidiano personale di economia, finanza e politica.',
        lang: 'it',
        start_url: base,
        scope: base,
        display: 'standalone',
        background_color: '#F6F7F9',
        theme_color: '#1B2433',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Solo l'interfaccia viene messa in cache dal service worker.
        // Le notizie per la lettura offline sono salvate dall'app con la loro data (vedi src/api.js).
        globPatterns: ['**/*.{js,css,html,svg,png}', '**/*-latin-*.woff2'],
        navigateFallback: 'index.html',
      },
    }),
  ],
});
