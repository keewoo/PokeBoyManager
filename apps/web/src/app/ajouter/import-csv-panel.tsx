"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { createImport } from "@/lib/api/imports";

/** Import CSV de la collection (mission `v6-import-export` point 1) : aucune clé IA requise
 * (contrairement aux photos) — le rapprochement au catalogue se fait sur le texte de chaque
 * ligne, pas sur une extraction visuelle. Redirige vers le MÊME écran de validation qu'une
 * reconnaissance photo, aucun écran de plus. */
export function ImportCsvPanel() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleImport() {
    if (!file || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createImport(file);
      router.push(`/ajouter/validation?uploads=${result.upload_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "L'import a échoué.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-6 rounded-lg border border-border bg-card p-4">
      <h3 className="font-heading text-base font-bold text-foreground">
        Importer une collection existante (CSV)
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Notre propre format d&rsquo;export ou un fichier générique (colonnes carte/numéro/
        extension, alias anglais acceptés) — chaque ligne est rapprochée du catalogue, puis
        proposée à la même validation qu&rsquo;une photo.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
          {fileName ?? "Choisir un fichier .csv"}
        </Button>
        <Button type="button" onClick={handleImport} disabled={!file || submitting}>
          {submitting ? "Import…" : "Importer"}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          aria-label="Choisir un fichier CSV"
          onChange={(event) => {
            const picked = event.target.files?.[0] ?? null;
            setFile(picked);
            setFileName(picked?.name ?? null);
          }}
        />
      </div>

      {error && (
        <div className="mt-3">
          <FormNotice variant="error">{error}</FormNotice>
        </div>
      )}
    </div>
  );
}
