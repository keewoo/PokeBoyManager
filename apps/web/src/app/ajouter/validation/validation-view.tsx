"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import {
  confirmAll,
  confirmDetection,
  getUpload,
  rejectDetection,
  retryRecognition,
  subscribeToUploadEvents,
  type Detection,
  type UploadDetail,
  decoupeDouteuse,
} from "@/lib/api/validation";
import { getApiBaseUrl } from "@/lib/config";

import { DetectionCard, type ConfirmForm, type SelectedCard } from "./detection-card";

type MergedDetection = { uploadId: string; detection: Detection };

function defaultForm(detection: Detection): ConfirmForm {
  return {
    language: detection.extraction?.language ?? "fr",
    variant: ["normal", "holo", "reverse_holo", "first_edition"].includes(
      detection.extraction?.variant ?? ""
    )
      ? (detection.extraction!.variant as string)
      : "normal",
    quantity: 1,
    // Pré-rempli depuis l'estimation automatique (lot `v3-etat`) quand elle existe, toujours
    // modifiable — jamais imposé : l'utilisateur reste le dernier mot sur l'état déclaré.
    conditionGrade: detection.condition?.overall_grade_label ?? "",
    purchasePrice: "",
  };
}

export function ValidationView({ uploadIds }: { uploadIds: string[] }) {
  const router = useRouter();
  const [uploads, setUploads] = useState<Record<string, UploadDetail>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<Record<string, number>>({});
  const [manualCards, setManualCards] = useState<Record<string, SelectedCard | null>>({});
  const [forms, setForms] = useState<Record<string, ConfirmForm>>({});
  const [retrying, setRetrying] = useState(false);
  const formsRef = useRef(forms);
  formsRef.current = forms;
  const manualCardsRef = useRef(manualCards);
  manualCardsRef.current = manualCards;
  const selectedCandidateRef = useRef(selectedCandidate);
  selectedCandidateRef.current = selectedCandidate;
  // Flux SSE ouverts, par envoi : gardés pour pouvoir en rouvrir un après une relance (le
  // précédent s'est fermé sur `done` quand le job a échoué).
  const streamsRef = useRef<Map<string, () => void>>(new Map());

  function openStream(id: string) {
    streamsRef.current.get(id)?.();
    const unsubscribe = subscribeToUploadEvents(
      id,
      (snapshot) => setUploads((prev) => ({ ...prev, [id]: snapshot })),
      () => {}
    );
    streamsRef.current.set(id, unsubscribe);
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const results = await Promise.all(uploadIds.map((id) => getUpload(id)));
        if (cancelled) return;
        const byId: Record<string, UploadDetail> = {};
        results.forEach((detail) => {
          byId[detail.upload_id] = detail;
        });
        setUploads(byId);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Impossible de charger les envois.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    uploadIds.forEach(openStream);

    const streams = streamsRef.current;
    return () => {
      cancelled = true;
      streams.forEach((unsubscribe) => unsubscribe());
      streams.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `uploadIds` vient de l'URL, stable pour la durée de vie de l'écran
  }, []);

  async function handleRetry() {
    const failedIds = uploadIds.filter((id) => uploads[id]?.job_status === "failed");
    if (failedIds.length === 0 || retrying) return;
    setRetrying(true);
    setError(null);
    try {
      await Promise.all(failedIds.map((id) => retryRecognition(id)));
      // Optimiste : on repasse l'envoi en « en file » et on rouvre son flux de progression (le
      // précédent s'est fermé quand le job avait échoué).
      setUploads((prev) => {
        const next = { ...prev };
        for (const id of failedIds) {
          if (next[id]) next[id] = { ...next[id], job_status: "queued", job_error: null };
        }
        return next;
      });
      failedIds.forEach(openStream);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "La relance a échoué.");
    } finally {
      setRetrying(false);
    }
  }

  const merged: MergedDetection[] = useMemo(() => {
    const rows: MergedDetection[] = [];
    for (const uploadId of uploadIds) {
      const detail = uploads[uploadId];
      if (!detail) continue;
      for (const detection of detail.detections) {
        rows.push({ uploadId, detection });
      }
    }
    return rows.sort((a, b) => a.detection.reading_order - b.detection.reading_order);
  }, [uploads, uploadIds]);

  useEffect(() => {
    setForms((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const { detection } of merged) {
        if (!(detection.id in next)) {
          next[detection.id] = defaultForm(detection);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [merged]);

  const pending = merged.filter((row) => row.detection.status === "pending");
  const activeId = pending[0]?.detection.id ?? null;
  // Nombre de cartes que « Tout ajouter » validerait maintenant (mêmes règles que
  // `pbm_api.validation.service.confirm_all` : un premier candidat présélectionné) — pas le
  // total des détections, dont certaines resteront `pending` (jeu de mots trop bruité).
  const autoConfirmableCount = pending.filter(
    (row) => row.detection.candidates?.[0]?.preselected
  ).length;
  const stillProcessing = uploadIds.some((id) => {
    const detail = uploads[id];
    return detail && (detail.job_status === "queued" || detail.job_status === "running");
  });
  // Un job en échec (mission `pbm-hotfix-reconnaissance` : le fournisseur IA a refusé la
  // requête, ou toute autre panne du pipeline de reconnaissance) doit se voir — jamais un écran
  // silencieux qui laisse croire qu'il n'y avait simplement rien à reconnaître.
  const failedUploads = uploadIds
    .map((id) => uploads[id])
    .filter((detail): detail is UploadDetail => !!detail && detail.job_status === "failed");
  const failedJobError = failedUploads.find((detail) => detail.job_error)?.job_error ?? null;

  function selectedCardFor(detection: Detection): SelectedCard | null {
    const manual = manualCardsRef.current[detection.id];
    if (manual) return manual;
    const index = selectedCandidateRef.current[detection.id] ?? 0;
    const candidate = detection.candidates?.[index];
    if (!candidate) return null;
    return {
      card_id: candidate.card_id,
      name: candidate.name,
      number: candidate.number,
      set_name: candidate.set_name,
    };
  }

  async function handleConfirm(row: MergedDetection) {
    const card = selectedCardFor(row.detection);
    if (!card) return;
    const form = formsRef.current[row.detection.id] ?? defaultForm(row.detection);
    try {
      await confirmDetection(row.detection.id, {
        card_id: card.card_id,
        language: form.language,
        variant: form.variant,
        quantity: form.quantity,
        condition_grade: form.conditionGrade || null,
        purchase_price: form.purchasePrice || null,
      });
      setUploads((prev) => {
        const detail = prev[row.uploadId];
        if (!detail) return prev;
        return {
          ...prev,
          [row.uploadId]: {
            ...detail,
            detections: detail.detections.map((detection) =>
              detection.id === row.detection.id
                ? { ...detection, status: "validated" as const }
                : detection
            ),
          },
        };
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "La validation a échoué.");
    }
  }

  async function handleReject(row: MergedDetection) {
    try {
      await rejectDetection(row.detection.id);
      setUploads((prev) => {
        const detail = prev[row.uploadId];
        if (!detail) return prev;
        return {
          ...prev,
          [row.uploadId]: {
            ...detail,
            detections: detail.detections.map((detection) =>
              detection.id === row.detection.id
                ? { ...detection, status: "rejected" as const }
                : detection
            ),
          },
        };
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Le rejet a échoué.");
    }
  }

  async function handleConfirmAll() {
    try {
      await Promise.all(uploadIds.map((id) => confirmAll(id)));
      const refreshed = await Promise.all(uploadIds.map((id) => getUpload(id)));
      const byId: Record<string, UploadDetail> = {};
      refreshed.forEach((detail) => {
        byId[detail.upload_id] = detail;
      });
      setUploads(byId);
      router.push("/collection");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "L'ajout groupé a échoué.");
    }
  }

  // Raccourcis clavier (mission point 2) : Entrée valide la détection active (première carte
  // encore `pending`, dans l'ordre de lecture), 1/2/3 changent son candidat sélectionné — jamais
  // quand le focus est dans un champ de saisie (recherche manuelle, langue, prix…).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (!activeId) return;
      const activeRow = merged.find((row) => row.detection.id === activeId);
      if (!activeRow) return;

      if (event.key === "Enter") {
        event.preventDefault();
        handleConfirm(activeRow);
      } else if (["1", "2", "3"].includes(event.key)) {
        const index = Number(event.key) - 1;
        if (activeRow.detection.candidates?.[index]) {
          event.preventDefault();
          setManualCards((prev) => ({ ...prev, [activeId]: null }));
          setSelectedCandidate((prev) => ({ ...prev, [activeId]: index }));
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- handleConfirm ferme sur des refs à jour
  }, [activeId, merged]);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  if (uploadIds.length === 0 || merged.length === 0) {
    if (failedJobError) {
      return (
        <EmptyState
          title="La reconnaissance a échoué"
          description={`Le fournisseur IA a signalé une erreur : ${failedJobError}`}
          action={{
            label: retrying ? "Relance en cours…" : "Relancer la reconnaissance",
            onClick: handleRetry,
          }}
        />
      );
    }
    return (
      <EmptyState
        title="Rien à valider"
        description="Envoie d'abord des photos pour lancer la reconnaissance."
        action={{ label: "Ajouter des photos", href: "/ajouter" }}
      />
    );
  }

  return (
    <div>
      <div className="mb-4 flex gap-2 text-sm font-medium text-muted-foreground" aria-hidden>
        <span className="rounded-full px-3 py-1">1 · Photos</span>
        <span className="rounded-full px-3 py-1">2 · Reconnaissance</span>
        <span className="rounded-full bg-secondary px-3 py-1 text-foreground">3 · Validation</span>
      </div>

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-heading text-xl font-bold text-foreground">
            {merged.length} carte{merged.length > 1 ? "s" : ""} trouvée
            {merged.length > 1 ? "s" : ""}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Rien n&rsquo;entre dans ta collection sans ton accord. Entrée valide la carte active,
            1/2/3 changent le candidat.
          </p>
        </div>
        <Button onClick={handleConfirmAll} disabled={autoConfirmableCount === 0}>
          Ajouter les {autoConfirmableCount} carte{autoConfirmableCount > 1 ? "s" : ""} validées
        </Button>
      </div>

      {error && (
        <div className="mb-4">
          <FormNotice variant="error">{error}</FormNotice>
        </div>
      )}

      {failedJobError && (
        <div className="mb-4 flex flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 sm:flex-1">
            <FormNotice variant="error">
              La reconnaissance a échoué sur une partie des photos : {failedJobError}
            </FormNotice>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRetry}
            disabled={retrying}
            className="shrink-0"
          >
            {retrying ? "Relance en cours…" : "Relancer la reconnaissance"}
          </Button>
        </div>
      )}

      {stillProcessing && (
        <p className="mb-3 text-sm text-muted-foreground">Reconnaissance en cours…</p>
      )}

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <div className="hidden lg:block">
          <div className="sticky top-4 rounded-lg border border-border bg-card p-3">
            <span className="text-xs font-semibold uppercase text-muted-foreground">
              Détection
            </span>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              {merged.map((row) => (
                // eslint-disable-next-line @next/next/no-img-element -- image servie par l'API
                <img
                  key={row.detection.id}
                  src={`${getApiBaseUrl()}${row.detection.crop_url}`}
                  alt=""
                  className="aspect-[63/88] w-full rounded bg-secondary object-cover"
                  onError={(event) => {
                    // Recadrage absent du stockage : tuile neutre, jamais l'icône « image cassée ».
                    event.currentTarget.style.visibility = "hidden";
                  }}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          {merged.map((row) => (
            <DetectionCard
              key={row.detection.id}
              detection={row.detection}
              isActive={row.detection.id === activeId}
              selectedCandidateIndex={
                selectedCandidate[row.detection.id] ??
                // Découpe douteuse : on ne propose RIEN. Un index hors bornes laisse
                // `selected` à null, donc « Valider » désactivé tant que l'utilisateur n'a
                // pas choisi — plutôt qu'un nom qui vient peut-être de la carte voisine.
                (decoupeDouteuse(row.detection) ? -1 : 0)
              }
              manualCard={manualCards[row.detection.id] ?? null}
              form={forms[row.detection.id] ?? defaultForm(row.detection)}
              onSelectCandidate={(index) =>
                setSelectedCandidate((prev) => ({ ...prev, [row.detection.id]: index }))
              }
              onManualCard={(card) =>
                setManualCards((prev) => ({ ...prev, [row.detection.id]: card }))
              }
              onFormChange={(form) =>
                setForms((prev) => ({ ...prev, [row.detection.id]: form }))
              }
              onConfirm={() => handleConfirm(row)}
              onReject={() => handleReject(row)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
