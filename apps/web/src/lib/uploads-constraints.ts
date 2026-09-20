// Doit rester aligné avec `pbm_api.uploads.service` (`ALLOWED_CONTENT_TYPES`,
// `upload_max_size_bytes`, `upload_max_files_per_batch`) — la validation ici n'est qu'un
// confort côté client, l'API revérifie tout (magic bytes compris). Le MPO (photos portrait/HDR
// des téléphones) arrive avec un type `image/jpeg`, donc déjà couvert ; `application/octet-stream`
// n'est pas listé ici pour garder un refus immédiat des fichiers manifestement hors sujet — un
// HEIC mal étiqueté est rattrapé par l'extension dans `guessContentType`.
export const ALLOWED_CONTENT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
  "image/webp",
];
export const MAX_SIZE_BYTES = 20 * 1024 * 1024;
export const MAX_FILES_PER_BATCH = 30;

// Heuristique volontairement simple (1 carte par photo) : ce lot ne sait pas encore compter
// les cartes avant reconnaissance (lot `v3-identification`) — juste donner un ordre de
// grandeur avant de lancer, affiché comme une estimation.
export const ESTIMATED_COST_PER_CARD_EUR = 0.006;

// iOS/Safari annonce parfois un `File.type` vide pour un HEIC ; on retombe sur l'extension.
export function guessContentType(file: File): string {
  if (file.type) {
    return file.type;
  }
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".heic")) return "image/heic";
  if (lower.endsWith(".heif")) return "image/heif";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".mpo")) return "image/jpeg";
  return "application/octet-stream";
}
