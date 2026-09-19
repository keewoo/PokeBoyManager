"use client";

import { useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import {
  deleteAiKey,
  getAiSettings,
  getAiUsage,
  listAiKeys,
  setDefaultProvider,
  testAiKey,
  upsertAiKey,
  type AiKeyResponse,
  type AiProvider,
  type AiUsageEntry,
} from "@/lib/api/ai-keys";

const PROVIDERS: {
  id: AiProvider;
  label: string;
  color: string;
  letter: string;
  consoleUrl: string;
  consoleLabel: string;
}[] = [
  {
    id: "anthropic",
    label: "Claude · Anthropic",
    color: "#C8663F",
    letter: "A",
    consoleUrl: "https://console.anthropic.com/settings/keys",
    consoleLabel: "console.anthropic.com",
  },
  {
    id: "gemini",
    label: "Gemini · Google",
    color: "#3E7BE6",
    letter: "G",
    consoleUrl: "https://aistudio.google.com/app/apikey",
    consoleLabel: "aistudio.google.com",
  },
  {
    id: "openai",
    label: "ChatGPT · OpenAI",
    color: "#10A37F",
    letter: "O",
    consoleUrl: "https://platform.openai.com/api-keys",
    consoleLabel: "platform.openai.com",
  },
];

type TestOutcome = { valid: boolean; message: string };

export function AiTab() {
  const [keys, setKeys] = useState<AiKeyResponse[] | null>(null);
  const [defaultProviderId, setDefaultProviderId] = useState<AiProvider | null>(null);
  const [usage, setUsage] = useState<AiUsageEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Partial<Record<AiProvider, string>>>({});
  const [editing, setEditing] = useState<Partial<Record<AiProvider, boolean>>>({});
  const [busy, setBusy] = useState<AiProvider | null>(null);
  const [testResults, setTestResults] = useState<Partial<Record<AiProvider, TestOutcome>>>({});
  const [rowError, setRowError] = useState<Partial<Record<AiProvider, string>>>({});

  async function load() {
    try {
      const [keyList, settings, usageEntries] = await Promise.all([
        listAiKeys(),
        getAiSettings(),
        getAiUsage(),
      ]);
      setKeys(keyList);
      setDefaultProviderId(settings.default_provider);
      setUsage(usageEntries);
    } catch (error) {
      setLoadError(
        error instanceof ApiError ? error.message : "Impossible de charger tes clés IA."
      );
    }
  }

  useEffect(() => {
    load();
  }, []);

  function keyFor(providerId: AiProvider): AiKeyResponse | undefined {
    return keys?.find((k) => k.provider === providerId);
  }

  async function handleSave(providerId: AiProvider) {
    const value = (inputs[providerId] ?? "").trim();
    if (!value) return;
    setBusy(providerId);
    setRowError((prev) => ({ ...prev, [providerId]: undefined }));
    try {
      await upsertAiKey(providerId, value);
      setInputs((prev) => ({ ...prev, [providerId]: "" }));
      setEditing((prev) => ({ ...prev, [providerId]: false }));
      setTestResults((prev) => ({ ...prev, [providerId]: undefined }));
      await load();
    } catch (error) {
      setRowError((prev) => ({
        ...prev,
        [providerId]: error instanceof ApiError ? error.message : "Impossible d'enregistrer cette clé.",
      }));
    } finally {
      setBusy(null);
    }
  }

  async function handleTest(providerId: AiProvider) {
    setBusy(providerId);
    setRowError((prev) => ({ ...prev, [providerId]: undefined }));
    try {
      const result = await testAiKey(providerId);
      setTestResults((prev) => ({ ...prev, [providerId]: result }));
    } catch (error) {
      setRowError((prev) => ({
        ...prev,
        [providerId]: error instanceof ApiError ? error.message : "Impossible de tester cette clé.",
      }));
    } finally {
      setBusy(null);
    }
  }

  async function handleDelete(providerId: AiProvider) {
    setBusy(providerId);
    try {
      await deleteAiKey(providerId);
      setTestResults((prev) => ({ ...prev, [providerId]: undefined }));
      await load();
    } catch (error) {
      setRowError((prev) => ({
        ...prev,
        [providerId]: error instanceof ApiError ? error.message : "Impossible de supprimer cette clé.",
      }));
    } finally {
      setBusy(null);
    }
  }

  async function handleSetDefault(providerId: AiProvider) {
    setBusy(providerId);
    try {
      const settings = await setDefaultProvider(providerId);
      setDefaultProviderId(settings.default_provider);
    } catch (error) {
      setRowError((prev) => ({
        ...prev,
        [providerId]: error instanceof ApiError ? error.message : "Impossible de définir le fournisseur par défaut.",
      }));
    } finally {
      setBusy(null);
    }
  }

  const totalCalls = usage.reduce((sum, entry) => sum + entry.calls_count, 0);
  const totalCost = usage.reduce((sum, entry) => sum + Number(entry.estimated_cost_eur), 0);

  return (
    <div className="flex max-w-2xl flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Ta clé sert uniquement à analyser tes photos et à générer les fiches. Elle est chiffrée
        et ne s&apos;affiche plus jamais en entier.
      </p>

      {loadError && <FormNotice variant="error">{loadError}</FormNotice>}

      {PROVIDERS.map((provider) => {
        const stored = keyFor(provider.id);
        const isDefault = defaultProviderId === provider.id;
        const isBusy = busy === provider.id;
        const testResult = testResults[provider.id];
        const isEditing = editing[provider.id] || !stored;

        return (
          <div
            key={provider.id}
            className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-3.5 rounded-xl border border-border bg-card p-3.5"
          >
            <span
              className="grid h-11 w-11 place-items-center rounded-xl text-base font-extrabold text-white"
              style={{ backgroundColor: provider.color }}
              aria-hidden
            >
              {provider.letter}
            </span>

            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <b className="text-sm text-foreground">{provider.label}</b>
                {!stored && <Badge variant="outline">non configurée</Badge>}
                {stored && testResult === undefined && <Badge variant="default">enregistrée</Badge>}
                {testResult?.valid === true && <Badge variant="success">valide</Badge>}
                {testResult?.valid === false && /quota/i.test(testResult.message) && (
                  <Badge variant="gold">quota dépassé</Badge>
                )}
                {testResult?.valid === false && !/quota/i.test(testResult.message) && (
                  <Badge variant="danger">invalide</Badge>
                )}
                {isDefault && <Badge variant="gold">par défaut</Badge>}
              </div>

              {stored && !isEditing && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{stored.key_mask}</span>
                  {testResult && (
                    <span className="text-xs text-muted-foreground">{testResult.message}</span>
                  )}
                </div>
              )}

              {isEditing && (
                <Input
                  type="password"
                  placeholder={`Colle ta clé API ${provider.label.split(" · ")[0]}`}
                  aria-label={`Clé API ${provider.label}`}
                  value={inputs[provider.id] ?? ""}
                  onChange={(event) =>
                    setInputs((prev) => ({ ...prev, [provider.id]: event.target.value }))
                  }
                  className="max-w-xs"
                />
              )}

              {rowError[provider.id] && (
                <p className="text-xs text-danger">{rowError[provider.id]}</p>
              )}

              <a
                href={provider.consoleUrl}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-muted-foreground underline underline-offset-2"
              >
                Créer une clé sur {provider.consoleLabel}
              </a>
            </div>

            <div className="grid justify-items-end gap-1.5">
              {isEditing ? (
                <Button
                  type="button"
                  size="sm"
                  disabled={isBusy || !(inputs[provider.id] ?? "").trim()}
                  onClick={() => handleSave(provider.id)}
                >
                  Enregistrer
                </Button>
              ) : (
                <>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isBusy}
                    onClick={() => handleTest(provider.id)}
                  >
                    Tester
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isBusy}
                    onClick={() => setEditing((prev) => ({ ...prev, [provider.id]: true }))}
                  >
                    Remplacer
                  </Button>
                  {!isDefault && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={isBusy}
                      onClick={() => handleSetDefault(provider.id)}
                    >
                      Définir par défaut
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isBusy}
                    onClick={() => handleDelete(provider.id)}
                  >
                    Supprimer
                  </Button>
                </>
              )}
            </div>
          </div>
        );
      })}

      <div className="mt-2 flex flex-col gap-2">
        <h3 className="font-heading text-base font-bold text-foreground">Usage</h3>
        <div className="flex gap-6 rounded-xl border border-border bg-card p-3.5">
          <div>
            <b className="text-lg text-foreground">{totalCalls}</b>
            <p className="text-xs text-muted-foreground">appels IA</p>
          </div>
          <div>
            <b className="text-lg text-foreground">{totalCost.toFixed(2)} €</b>
            <p className="text-xs text-muted-foreground">coût estimé sur tes clés</p>
          </div>
        </div>
      </div>
    </div>
  );
}
