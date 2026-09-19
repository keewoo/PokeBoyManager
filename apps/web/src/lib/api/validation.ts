import { apiGet, apiJson } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/config";

export type DetectionStatus = "pending" | "validated" | "rejected";

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
};

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type UploadDetail = {
  upload_id: string;
  status: string;
  job_status: JobStatus | null;
  job_error: string | null;
  detections: Detection[];
};

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

export type ConfirmDetectionResult = {
  detection_id: string;
  status: DetectionStatus;
  collection_item_ids: string[];
};

export type RejectDetectionResult = {
  detection_id: string;
  status: DetectionStatus;
};

export type ConfirmAllResult = {
  upload_id: string;
  confirmed: string[];
  skipped: string[];
};

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

export function getUpload(uploadId: string): Promise<UploadDetail> {
  return apiGet<UploadDetail>(`/uploads/${uploadId}`);
}

export function confirmDetection(
  detectionId: string,
  payload: ConfirmDetectionPayload
): Promise<ConfirmDetectionResult> {
  return apiJson<ConfirmDetectionResult>("POST", `/detections/${detectionId}/confirm`, payload);
}

export function rejectDetection(detectionId: string): Promise<RejectDetectionResult> {
  return apiJson<RejectDetectionResult>("POST", `/detections/${detectionId}/reject`);
}

export function confirmAll(uploadId: string): Promise<ConfirmAllResult> {
  return apiJson<ConfirmAllResult>("POST", `/uploads/${uploadId}/confirm-all`);
}

export async function searchCatalog(query: string): Promise<CardSearchResult[]> {
  if (!query.trim()) return [];
  const params = new URLSearchParams({ q: query });
  return apiGet<CardSearchResult[]>(`/catalog/search?${params.toString()}`);
}

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
