import { apiUpload } from "@/lib/api/client";

export type ImportCsvResult = {
  upload_id: string;
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
};

/** Import CSV de la collection (mission `v6-import-export` point 1) : un `Job` créé côté API,
 * rapproché du catalogue puis proposé à l'écran de validation existant
 * (`/ajouter/validation?uploads=<upload_id>`) — même parcours qu'une photo. */
export function createImport(file: File): Promise<ImportCsvResult> {
  return apiUpload<ImportCsvResult>("/me/imports", file);
}
