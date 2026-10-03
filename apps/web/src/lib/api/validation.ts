import { apiGet, apiJson } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

/** État d'une détection de carte : en attente d'arbitrage, validée, ou rejetée par l'utilisateur. */
export type DetectionStatus = "pending" | "validated" | "rejected";

/** Une carte du catalogue proposée comme correspondance d'une détection, avec ses scores et la présélection éventuelle (décidés serveur). */
export type IdentificationCandidate = {
  card_id: string;
  set_id: string;
  name: string;
  number: string;
  set_name: string;
  set_code: string;
  catalog_score: number;
  combined_score: number;
  preselected: boolean;
};

/** Champs lus sur la carte par la reconnaissance (nom, numéro, set, langue…), chacun assorti d'un indice de confiance. */
export type CardExtraction = {
  name: string | null;
  name_confidence: number;
  number: string | null;
  number_confidence: number;
  total: number | null;
  total_confidence: number;
  set_code: string | null;
  set_code_confidence: number;
  language: string | null;
  language_confidence: number;
  hp: number | null;
  hp_confidence: number;
  card_type: string | null;
  card_type_confidence: number;
  variant: string | null;
  variant_confidence: number;
};

/** Forme écrite par `pbm_api.state.service` (lot `v3-etat`) — `DetectionResponse.condition` est
 * un `dict` non typé côté API (`{[key: string]: unknown}` dans le schéma OpenAPI généré). */
export type ConditionAssessment = {
  overall_grade_label: string | null;
  score_10: number | null;
  counterfeit_suspected: boolean;
  counterfeit_reasons: string[];
};

/** Une carte détectée dans une photo : son recadrage, l'extraction, les candidats du catalogue, l'état estimé et la qualité du découpage. */
export type Detection = {
  id: string;
  reading_order: number;
  status: DetectionStatus;
  crop_url: string;
  extraction: CardExtraction | null;
  candidates: IdentificationCandidate[] | null;
  condition: ConditionAssessment | null;
  // "visuel" (index visuel, aucun appel IA), "ia", "aucun" ou `null` (pas encore traitée) —
  // lot `v3-identification-visuelle`, sert au badge « reconnue sans IA ».
  identification_method: "visuel" | "ia" | "aucun" | null;
  // Verdict sur le recadrage (lot `h1-decoupe-fiable`). `seam` vrai = une arête droite
  // traverse le cadre : deux cartes s'y partagent probablement la place, et le nom proposé
  // vient peut-être de la voisine. `null` pour les détections antérieures au lot.
  crop_quality: {
    seam: boolean;
    score: number;
    axis: string | null;
    // Part du cadre qui n'est pas la carte visée : jointure avec la voisine, ou carte qui
    // déborde de la photo. C'est le seuil de 30 % de la règle de seconde passe (JF, 22/09).
    truncated?: number;
    reason?: string | null;
  } | null;
};

/** Seuil de la règle de JF : au-delà, ce qu'on identifie n'est plus la carte. */
export const SEUIL_TRONCATURE = 0.3;

/** Découpe à cheval, ou carte amputée de 30 % : rien n'est présélectionné, l'utilisateur tranche. */
export function decoupeDouteuse(detection: Detection): boolean {
  const qualite = detection.crop_quality;
  if (!qualite) return false;
  return qualite.seam === true || (qualite.truncated ?? 0) >= SEUIL_TRONCATURE;
}

/** État d'un job de reconnaissance côté serveur (en file, en cours, réussi, échoué). */
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

/** Détail d'un envoi en cours de reconnaissance : statut, état du job (et son erreur), et les détections obtenues. */
export type UploadDetail = {
  upload_id: string;
  status: string;
  job_status: JobStatus | null;
  job_error: string | null;
  detections: Detection[];
};

/** Choix de l'utilisateur au moment de confirmer une détection : la carte retenue et les attributs de l'exemplaire à créer. */
export type ConfirmDetectionPayload = {
  card_id: string;
  language?: string;
  variant?: string;
  quantity?: number;
  condition_grade?: string | null;
  purchase_price?: string | null;
  purchase_currency?: string | null;
  acquired_at?: string | null;
};

/** Résultat d'une confirmation : la détection passe `validated` et les exemplaires de collection créés sont renvoyés. */
export type ConfirmDetectionResult = {
  detection_id: string;
  status: DetectionStatus;
  collection_item_ids: string[];
};

/** Résultat d'un rejet : la détection passe `rejected`, aucun exemplaire n'est créé. */
export type RejectDetectionResult = {
  detection_id: string;
  status: DetectionStatus;
};

/** Résultat d'une confirmation en masse : les détections confirmées et celles laissées de côté. */
export type ConfirmAllResult = {
  upload_id: string;
  confirmed: string[];
  skipped: string[];
};

/** Une carte trouvée par la recherche manuelle au catalogue, quand l'utilisateur corrige une détection. */
export type CardSearchResult = {
  card_id: string;
  set_id: string;
  number: string;
  name: string;
  matched_name: string;
  language: string | null;
  set_name: string;
  set_code: string;
  score: number;
};

/** Lit l'état d'un envoi et ses détections (`GET /uploads/{id}`), pour l'écran de validation. */
export function getUpload(uploadId: string): Promise<UploadDetail> {
  return apiGet<UploadDetail>(`/uploads/${uploadId}`);
}

/** Confirme une détection (`POST /detections/{id}/confirm`) : le serveur crée les exemplaires de collection correspondants. */
export function confirmDetection(
  detectionId: string,
  payload: ConfirmDetectionPayload
): Promise<ConfirmDetectionResult> {
  return apiJson<ConfirmDetectionResult>("POST", `/detections/${detectionId}/confirm`, payload);
}

/** Rejette une détection (`POST /detections/{id}/reject`) ; rien n'est ajouté à la collection. */
export function rejectDetection(detectionId: string): Promise<RejectDetectionResult> {
  return apiJson<RejectDetectionResult>("POST", `/detections/${detectionId}/reject`);
}

/** Confirme toutes les détections présélectionnables d'un envoi (`POST /uploads/{id}/confirm-all`) ; le serveur choisit lesquelles sont sûres. */
export function confirmAll(uploadId: string): Promise<ConfirmAllResult> {
  return apiJson<ConfirmAllResult>("POST", `/uploads/${uploadId}/confirm-all`);
}

/** Accusé de relance de la reconnaissance : l'envoi concerné et le nouveau job. */
export type RetryRecognitionResult = {
  upload_id: string;
  job_id: string;
  status: JobStatus;
};

/** Relance la reconnaissance d'un envoi (lot `pbm-parcours-validation`, mission point 6) après
 * un job en échec ou un délai dépassé — sans renvoyer la photo. */
export function retryRecognition(uploadId: string): Promise<RetryRecognitionResult> {
  return apiJson<RetryRecognitionResult>("POST", `/uploads/${uploadId}/retry-recognition`);
}

/** Recherche manuelle au catalogue (`GET /catalog/search`) pour corriger une détection ; requête vide → liste vide, sans appel. */
export async function searchCatalog(query: string): Promise<CardSearchResult[]> {
  if (!query.trim()) return [];
  const params = new URLSearchParams({ q: query });
  return apiGet<CardSearchResult[]>(`/catalog/search?${params.toString()}`);
}

/** URL de l'image officielle d'une carte du catalogue (`/img/cards/{id}`), en basse ou haute définition. */
export function cardImageUrl(cardId: string, size: "high" | "low" = "low"): string {
  return `${getApiBaseUrl()}/img/cards/${cardId}?size=${size}`;
}

/** Flux SSE de progression d'un envoi (`GET /uploads/{id}/events`) : `EventSource` envoie le
 * cookie de session automatiquement (`withCredentials`), pas d'en-tête `Authorization` à poser
 * — même mécanisme que les autres routes (`credentials: "include"` dans `lib/api/client.ts`). */
export function subscribeToUploadEvents(
  uploadId: string,
  onSnapshot: (snapshot: UploadDetail) => void,
  onDone: () => void
): () => void {
  const source = new EventSource(`${getApiBaseUrl()}/uploads/${uploadId}/events`, {
    withCredentials: true,
  });

  source.addEventListener("snapshot", (event) => {
    onSnapshot(JSON.parse((event as MessageEvent).data) as UploadDetail);
  });
  source.addEventListener("done", () => {
    onDone();
    source.close();
  });
  source.addEventListener("timeout", () => {
    onDone();
    source.close();
  });
  source.onerror = () => {
    // Le navigateur retente une connexion SSE par défaut ; une fois le job terminé côté
    // serveur, il n'y a plus rien à relire — fermer évite une boucle de reconnexions inutiles.
    source.close();
    onDone();
  };

  return () => source.close();
}
