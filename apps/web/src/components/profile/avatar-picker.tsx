"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { avatarUrl, uploadAvatar } from "@/lib/api/profile";

export type AvatarPickerProps = {
  hasAvatar: boolean;
  initials: string;
  onUploaded: () => void;
};

export function AvatarPicker({ hasAvatar, initials, onUploaded }: AvatarPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bust, setBust] = useState(() => Date.now());

  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setBusy(true);
    setError(null);
    try {
      await uploadAvatar(file);
      setBust(Date.now());
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'envoyer cette photo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-4">
      <span className="grid h-16 w-16 shrink-0 place-items-center overflow-hidden rounded-full bg-secondary text-lg font-bold text-secondary-foreground">
        {hasAvatar ? (
          // Avatar privé servi par l'API derrière le cookie de session — pas d'URL signée
          // nécessaire, `crossOrigin` fait suivre le cookie sur cette requête cross-origin.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={avatarUrl(bust)}
            alt=""
            crossOrigin="use-credentials"
            className="h-full w-full object-cover"
          />
        ) : (
          initials
        )}
      </span>
      <div className="flex flex-col gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? "Envoi…" : "Changer la photo"}
        </Button>
        <span className="text-xs text-muted-foreground">JPEG ou PNG · recadrée en carré</span>
        {error && <span className="text-xs text-danger">{error}</span>}
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png"
          className="hidden"
          aria-label="Changer la photo de profil"
          onChange={handleChange}
        />
      </div>
    </div>
  );
}
