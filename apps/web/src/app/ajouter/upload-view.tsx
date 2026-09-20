"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  completeUpload,
  createUploads,
  hasAnyAiKey,
  listPendingValidations,
  type PendingUpload,
  putRawBytes,
  type UploadTarget,
} from "@/lib/api/uploads";
import {
  ALLOWED_CONTENT_TYPES,
  ESTIMATED_COST_PER_CARD_EUR,
  MAX_FILES_PER_BATCH,
  MAX_SIZE_BYTES,
  guessContentType,
} from "@/lib/uploads-constraints";
import { cn } from "@/lib/utils";

type ItemStatus = "pending" | "uploading" | "processing" | "done" | "error";

type UploadItem = {
  id: string;
  file: File;
  contentType: string;
  previewUrl: string;
  status: ItemStatus;
  errorMessage?: string;
};

const STATUS_LABEL: Record<ItemStatus, string> = {
  pending: "Prête à envoyer",
  uploading: "Envoi…",
  processing: "Analyse…",
  done: "Envoyée",
  error: "Erreur",
};

function formatSize(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatEuros(value: number): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(value);
}

// Les navigateurs ne savent pas afficher un HEIC/HEIF dans un <img> : une URL d'objet Blob HEIC
// rend l'icône « image cassée » constatée en production (JF, 20/09) AVANT même l'envoi. Pour ces
// formats — et pour tout aperçu qui échoue à charger — on montre une tuile neutre, jamais une
// image brisée (mission point 3).
const UNRENDERABLE_PREVIEW_TYPES = new Set(["image/heic", "image/heif"]);

function PreviewThumb({ url, contentType }: { url: string; contentType: string }) {
  const [failed, setFailed] = useState(false);
  if (UNRENDERABLE_PREVIEW_TYPES.has(contentType) || failed) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-secondary text-muted-foreground">
        <span aria-hidden className="text-xl">
          🖼️
        </span>
        <span className="px-1 text-center text-[10px] leading-tight">Aperçu indisponible</span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- aperçu local (objet Blob), pas une image distante
    <img
      src={url}
      alt=""
      className="h-full w-full object-cover"
      onError={() => setFailed(true)}
    />
  );
}

type PendingGroup = { ids: string[]; pendingCount: number; createdAt: string };

// Un envoi = une photo côté API ; l'écran de validation en regroupe plusieurs par l'URL. On
// reconstitue le lot d'origine en regroupant les envois par horodatage à la seconde (ceux d'un
// même « Lancer la reconnaissance »), pour proposer une seule reprise par lot.
function groupPending(uploads: PendingUpload[]): PendingGroup[] {
  const map = new Map<string, PendingGroup>();
  for (const upload of uploads) {
    const key = upload.created_at.slice(0, 19);
    const group = map.get(key) ?? { ids: [], pendingCount: 0, createdAt: upload.created_at };
    group.ids.push(upload.upload_id);
    group.pendingCount += upload.pending_count;
    map.set(key, group);
  }
  return [...map.values()];
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function UploadView() {
  const router = useRouter();
  const [aiKeyStatus, setAiKeyStatus] = useState<"loading" | "missing" | "ready">("loading");
  const [items, setItems] = useState<UploadItem[]>([]);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [isLaunching, setIsLaunching] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const previewUrls = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    hasAnyAiKey().then((present) => {
      if (!cancelled) setAiKeyStatus(present ? "ready" : "missing");
    });
    // Envois anciens encore à valider (mission point 2) : un lot dont la reconnaissance a abouti
    // mais qui n'a jamais été validé ne doit pas être perdu — on le propose à la reprise.
    listPendingValidations().then((list) => {
      if (!cancelled) setPendingUploads(list);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const pendingGroups = useMemo(() => groupPending(pendingUploads), [pendingUploads]);

  useEffect(() => {
    const urls = previewUrls.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  function addFiles(fileList: FileList | File[]) {
    setBatchError(null);
    const incoming = Array.from(fileList);
    const activeCount = items.filter((item) => item.status !== "error").length;
    if (activeCount + incoming.length > MAX_FILES_PER_BATCH) {
      setBatchError(`${MAX_FILES_PER_BATCH} photos maximum par envoi (${activeCount} déjà ajoutées).`);
      return;
    }

    const next: UploadItem[] = incoming.map((file) => {
      const contentType = guessContentType(file);
      const previewUrl = URL.createObjectURL(file);
      previewUrls.current.add(previewUrl);
      const base = { id: crypto.randomUUID(), file, contentType, previewUrl };

      if (!ALLOWED_CONTENT_TYPES.includes(contentType)) {
        return {
          ...base,
          status: "error" as const,
          errorMessage: `« ${file.name} » : format non accepté (JPEG, PNG, HEIC, WEBP).`,
        };
      }
      if (file.size > MAX_SIZE_BYTES) {
        return { ...base, status: "error" as const, errorMessage: "Dépasse 20 Mo." };
      }
      return { ...base, status: "pending" as const };
    });

    setItems((prev) => [...prev, ...next]);
  }

  function removeItem(id: string) {
    setItems((prev) => {
      const target = prev.find((item) => item.id === id);
      if (target) {
        URL.revokeObjectURL(target.previewUrl);
        previewUrls.current.delete(target.previewUrl);
      }
      return prev.filter((item) => item.id !== id);
    });
  }

  const readyItems = items.filter((item) => item.status === "pending");
  const estimatedCards = readyItems.length;
  const estimatedCost = estimatedCards * ESTIMATED_COST_PER_CARD_EUR;

  async function launchRecognition() {
    if (readyItems.length === 0 || isLaunching) return;
    setIsLaunching(true);
    setBatchError(null);

    let targets: UploadTarget[];
    try {
      targets = await createUploads(
        readyItems.map((item) => ({
          filename: item.file.name,
          content_type: item.contentType,
          size_bytes: item.file.size,
        }))
      );
    } catch (error) {
      setBatchError(error instanceof ApiError ? error.message : "L'envoi a échoué.");
      setIsLaunching(false);
      return;
    }

    const completedUploadIds: string[] = [];
    for (const [item, target] of readyItems.map((item, index) => [item, targets[index]] as const)) {
      if (!target) continue;
      setItems((prev) =>
        prev.map((current) => (current.id === item.id ? { ...current, status: "uploading" } : current))
      );
      try {
        await putRawBytes(target, item.file);
        setItems((prev) =>
          prev.map((current) => (current.id === item.id ? { ...current, status: "processing" } : current))
        );
        const completed = await completeUpload(target.upload_id);
        if (completed.recognition_enabled) completedUploadIds.push(completed.upload_id);
        setItems((prev) =>
          prev.map((current) => (current.id === item.id ? { ...current, status: "done" } : current))
        );
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "L'envoi a échoué.";
        setItems((prev) =>
          prev.map((current) =>
            current.id === item.id ? { ...current, status: "error", errorMessage: message } : current
          )
        );
      }
    }

    setIsLaunching(false);
    if (completedUploadIds.length > 0) {
      router.push(`/ajouter/validation?uploads=${completedUploadIds.join(",")}`);
    }
  }

  if (aiKeyStatus === "loading") {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  if (aiKeyStatus === "missing") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-card px-6 py-16 text-center">
        <h2 className="font-heading text-xl font-bold text-foreground">Ajouter des photos</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Aucune clé IA n&rsquo;est configurée : la reconnaissance automatique est désactivée.
          L&rsquo;ajout manuel d&rsquo;une carte au catalogue reste toujours possible.
        </p>
        <Button asChild className="mt-2">
          <Link href="/profil">Configurer une clé dans Profil → Mon IA</Link>
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2 text-sm font-medium text-muted-foreground" aria-hidden>
        <span className="rounded-full bg-secondary px-3 py-1 text-foreground">1 · Photos</span>
        <span className="rounded-full px-3 py-1">2 · Reconnaissance</span>
        <span className="rounded-full px-3 py-1">3 · Validation</span>
      </div>

      <h2 className="font-heading text-xl font-bold text-foreground">Ajouter des photos</h2>
      <p className="mb-5 mt-1.5 text-sm text-muted-foreground">
        Une carte par photo ou tout un classeur : on détecte chaque carte. Les données de
        position (EXIF) sont supprimées à l&rsquo;envoi.
      </p>

      {pendingGroups.length > 0 && (
        <div className="mb-5 rounded-lg border border-border bg-card p-4">
          <h3 className="font-heading text-base font-bold text-foreground">À valider</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Des cartes reconnues attendent ta validation — reprends là où tu t&rsquo;es arrêté.
          </p>
          <ul className="mt-3 space-y-2">
            {pendingGroups.map((group) => (
              <li
                key={group.ids.join(",")}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
              >
                <span className="text-sm text-foreground">
                  <span className="font-medium">
                    {group.pendingCount} carte{group.pendingCount > 1 ? "s" : ""}
                  </span>{" "}
                  · <span className="text-muted-foreground">{formatDateTime(group.createdAt)}</span>
                </span>
                <Button asChild size="sm" variant="outline">
                  <Link href={`/ajouter/validation?uploads=${group.ids.join(",")}`}>Reprendre</Link>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div
        className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border bg-card px-6 py-12 text-center"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          addFiles(event.dataTransfer.files);
        }}
      >
        <div
          className="grid h-10 w-10 place-items-center rounded-full bg-secondary text-xl font-bold text-foreground"
          aria-hidden
        >
          +
        </div>
        <h3 className="font-heading text-base font-bold text-foreground">Glisse tes photos ici</h3>
        <p className="text-sm text-muted-foreground">
          JPEG, PNG, HEIC, WEBP · 20 Mo max par photo · 30 photos par envoi
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-2">
          <Button type="button" onClick={() => fileInputRef.current?.click()}>
            Choisir des fichiers
          </Button>
          <Button type="button" variant="outline" onClick={() => cameraInputRef.current?.click()}>
            Prendre une photo
          </Button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.heic,.heif"
          multiple
          className="hidden"
          aria-label="Choisir des fichiers"
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          aria-label="Prendre une photo"
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {batchError && (
        <div className="mt-3">
          <FormNotice variant="error">{batchError}</FormNotice>
        </div>
      )}

      {items.length > 0 && (
        <>
          <h3 className="mb-2.5 mt-6 font-heading text-base font-bold text-foreground">Prêtes à envoyer</h3>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {items.map((item) => (
              <li key={item.id} className="rounded-lg border border-border bg-card p-2 text-left text-xs">
                <div className="mb-1.5 aspect-square overflow-hidden rounded-md bg-secondary">
                  <PreviewThumb url={item.previewUrl} contentType={item.contentType} />
                </div>
                <p className="truncate font-medium text-foreground">{item.file.name}</p>
                <p className="text-muted-foreground">{formatSize(item.file.size)}</p>
                <p
                  className={cn(
                    "mt-0.5 font-medium",
                    item.status === "error" && "text-danger-foreground",
                    item.status === "done" && "text-success-foreground"
                  )}
                >
                  {STATUS_LABEL[item.status]}
                  {item.errorMessage ? ` — ${item.errorMessage}` : ""}
                </p>
                {item.status === "pending" && (
                  <button
                    type="button"
                    className="mt-1 text-muted-foreground underline"
                    onClick={() => removeItem(item.id)}
                  >
                    Retirer
                  </button>
                )}
              </li>
            ))}
          </ul>

          {readyItems.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3">
              <div>
                <p className="text-sm font-bold text-foreground">
                  ≈ {estimatedCards} carte{estimatedCards > 1 ? "s" : ""} · ≈ {formatEuros(estimatedCost)} sur ta
                  clé
                </p>
                <p className="text-xs text-muted-foreground">Estimation avant analyse, coût réel mesuré ensuite</p>
              </div>
              <Button type="button" onClick={launchRecognition} disabled={isLaunching}>
                {isLaunching ? "Envoi en cours…" : "Lancer la reconnaissance"}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
