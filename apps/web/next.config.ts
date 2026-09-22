import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Sortie autonome (lot `pbm-deploy`) : `.next/standalone/server.js` embarque un serveur Node
  // minimal + les seules dépendances runtime, exécuté par systemd sur kailo-srv sans `next start`
  // ni `node_modules` complet. `.next/static` et `public/` sont copiés à côté au déploiement.
  output: "standalone",
  // Les 99 fonds de remplacement (`public/fonds/`) ne changent jamais : on les sert avec un cache
  // long et immuable (lot `pbm-carte-remplacement`, point performance). Ne s'applique qu'aux
  // réponses servies par le serveur Next ; si un reverse-proxy sert `/fonds` en amont, régler le
  // cache là-bas aussi.
  async headers() {
    return [
      {
        source: "/fonds/:file*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
    ];
  },
};

export default nextConfig;
