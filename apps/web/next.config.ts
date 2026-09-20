import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Sortie autonome (lot `pbm-deploy`) : `.next/standalone/server.js` embarque un serveur Node
  // minimal + les seules dépendances runtime, exécuté par systemd sur kailo-srv sans `next start`
  // ni `node_modules` complet. `.next/static` et `public/` sont copiés à côté au déploiement.
  output: "standalone",
};

export default nextConfig;
