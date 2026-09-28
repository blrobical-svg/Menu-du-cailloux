// Menu Caillou : fonctionne hors ligne. La page est toujours redemandée en priorité (jamais de vieille version si on est en ligne).
const CACHE = 'menu-caillou-v2';
const COQUILLE = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.all(COQUILLE.map(u => c.add(u).catch(() => {}))))   // un fichier absent ne bloque plus l'installation
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(noms => Promise.all(noms.filter(n => n !== CACHE).map(n => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // Prix : réseau d'abord, dernier fichier connu si on est hors ligne
  if (url.pathname.endsWith('/prix.json')) {
    e.respondWith(
      fetch(req)
        .then(r => { if (r.ok) { const copie = r.clone(); caches.open(CACHE).then(c => c.put('prix.json', copie)); } return r; })
        .catch(() => caches.match('prix.json'))
    );
    return;
  }

  // Page : réseau d'abord (4 s maximum), sinon la dernière version connue
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      const reseau = fetch(req);
      try {
        const r = await Promise.race([reseau, new Promise((_, rej) => setTimeout(() => rej(new Error('lent')), 4000))]);
        if (r && r.ok && !r.redirected) { const c = await caches.open(CACHE); c.put('index.html', r.clone()); c.put('./', r.clone()); }
        return r;
      } catch (err) {
        const enCache = (await caches.match('index.html')) || (await caches.match('./'));
        return enCache || reseau;
      }
    })());
    return;
  }

  // Le reste (icônes, manifeste) : version en cache tout de suite, mise à jour en arrière-plan
  e.respondWith(
    caches.match(req, {ignoreSearch: true}).then(enCache => {
      const reseau = fetch(req)
        .then(r => { if (r.ok) { const copie = r.clone(); caches.open(CACHE).then(c => c.put(req, copie)); } return r; })
        .catch(() => enCache);
      return enCache || reseau;
    })
  );
});
