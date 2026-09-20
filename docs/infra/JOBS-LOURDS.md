# Traitements lourds sur la flotte — jamais sur la machine qui sert

> Règle d'or de la flotte (`~/.claude/CLAUDE.md` de devAI) : **on ne construit pas sur la machine
> qui sert.** Les traitements qui balaient tout le catalogue tournent sur **chimera** ; **seul le
> résultat** est importé en PROD (`kailo-srv`) par une commande courte. Lot fondateur :
> `pbm-jobs-flotte` (2026-09-20).

## Pourquoi (la faute qu'on ne refait pas)

Le relevé quotidien des prix (~22 000 cartes, appels réseau vers TCGdex + Pokémon TCG API) avait
été planifié dans le **worker de PROD**, sur `kailo-srv` (2 cœurs / ~4 Go, qui sert AUSSI kailo.life
et ACX). Résultat mesuré le 20/09/2026 : **1 h 20 de traitement pour zéro prix écrit**, un job resté
« running », le service dégradé. Un relevé complet, un import de catalogue ou un scraping de site
tiers n'ont rien à faire sur la machine qui répond aux visiteurs.

## Qui fait quoi

```
              chimera (16 threads, 32 Go, pbm_catalogue_ref)                 kailo-srv (PROD)
  ┌──────────────────────────────────────────────────────┐        ┌───────────────────────────┐
  │ 1. RELÈVE (lourd) : prix de TOUTES les cartes + taux   │        │ worker arq : COURT seulement│
  │    BCE  → écrits dans pbm_catalogue_ref                │        │  - detect_cards (photos)    │
  │    scripts/fleet_reference_daily.py                    │        │  - export_user_data (RGPD)  │
  │ 2. EXPORTE seulement les lignes du jour → TSV compressé│        │  - e-mails                  │
  │    infra/fleet/export_prices.sql / export_rates.sql    │        │ AUCUN cron lourd            │
  └───────────────┬────────────────────────────────────────┘        │ (HEAVY_JOBS_ENABLED=false)  │
                  │ scp (via devAI, relais)                           └─────────────▲─────────────┘
                  ▼                                                                 │ COPY + upsert
       ┌──────────────────────┐   scp    ┌──────────────────────┐   sudo -u postgres psql
       │ devAI (toujours allumé│ ───────▶ │ bundle sur kailo-srv  │ ──▶ infra/fleet/import_daily.sql
       │  orchestre + journalise)         │  /tmp/pbm-import/*.tsv │      (table temporaire → upsert,
       └──────────────────────┘          └──────────────────────┘       jointure cards.tcgdex_id)
```

- **La clé de jointure entre bases est `cards.tcgdex_id`**, jamais l'UUID `cards.id` : les deux
  bases sont seedées indépendamment, leurs UUID diffèrent. `tcgdex_id` est l'identifiant
  d'idempotence de l'import TCGdex — identique des deux côtés (22 169 cartes de part et d'autre).
- **PROD ne recalcule rien** : elle reçoit un TSV et fait `COPY` dans une table temporaire puis un
  upsert. Le seul calcul local est `REFRESH MATERIALIZED VIEW card_value_rank` (rang de valeur lu
  par la fiche), sur des données déjà importées — pas un scraping, mesuré léger (voir plus bas).

## La garde applicative (`HEAVY_JOBS_ENABLED`)

- `pbm_api.config.Settings.heavy_jobs_allowed` : **faux par défaut en production**, vrai hors
  production (dev/CI/chimera). Surchargeable par la variable d'environnement `HEAVY_JOBS_ENABLED`
  (`true`/`false`). Le `.env` de PROD pose `HEAVY_JOBS_ENABLED=false` (ceinture + bretelles).
- `pbm_api.worker` :
  - `WorkerSettings.cron_jobs` = **vide** quand c'est interdit → PROD ne PLANIFIE aucun relevé.
  - les tâches lourdes (`daily_prices_task`, `daily_exchange_rates_task`, `import_catalogue_task`,
    `weekly_incremental_import`, `weekly_tournament_presence_task`) **REFUSENT** explicitement si
    elles sont enfilées quand même : un `Job` en échec avec un message clair dans `jobs.error`,
    jamais une exécution à moitié (`_refuse_heavy_job`).
  - les jobs COURTS (`detect_cards`, `export_user_data`) ne sont pas concernés : enfilés à la
    demande depuis l'API, ils restent servis en PROD.

## Planification (agents launchd sur devAI)

| Agent launchd | Quand | Script | Fait |
|---|---|---|---|
| `ai.upgreg.pbm-prices-daily` | 05:30 Europe/Paris | `~/dev/pbm/jobs/prices-daily.sh` | relève+exporte sur chimera, rapatrie, importe en PROD, compte |
| `ai.upgreg.pbm-catalog-weekly` | Lundi 04:30 | `~/dev/pbm/jobs/catalog-weekly.sh` | import incrémental + tournoi sur chimera, exporte, importe |
| `ai.upgreg.pbm-prices-probe` | 09:00 Europe/Paris | `~/dev/pbm/jobs/prices-probe.sh` | **sonde honnête** : si 0 prix du jour en PROD → PANNE visible |

- SSH de chimera **coupe souvent** : chaque appel est réessayé (`~/dev/pbm/cw.sh`), et le relevé
  long tourne **détaché** sur chimera (marqueur de fin), sondé jusqu'à complétion — une coupure ne
  relance pas le relevé de zéro.
- **On ne conclut jamais au succès sans avoir compté** les lignes réellement présentes en PROD.
- Journaux : `~/dev/logs/pbm-prices-daily.log`, `…-catalog-weekly.log`, `…-prices-probe.log`.
- État lisible : `~/dev/pbm/jobs/state/prices.json` (dernier jour importé, nombre, verdict).

## La sonde honnête

À 09:00, `prices-probe.sh` interroge la PROD :
```sql
SELECT count(*) FROM card_prices_daily WHERE day = current_date;
```
Si le compte est **0**, c'est une **PANNE** (pas un silence) : ligne d'alerte dans le journal,
`verdict:"PANNE"` dans `state/prices.json`, et un e-mail à `direction@upgreg.ai`. Un enchaînement
qui finit sans rien écrire est une panne, jamais un succès.

## Commandes (exploitation)

```bash
# --- Lancer la chaîne quotidienne à la main (depuis devAI) ---
bash ~/dev/pbm/jobs/prices-daily.sh            # relève+exporte+importe+compte, journalise
bash ~/dev/pbm/jobs/prices-probe.sh            # vérifie l'état du jour en PROD
bash ~/dev/pbm/jobs/catalog-weekly.sh          # import hebdo du catalogue

# --- Étapes unitaires ---
# 1) relève sur chimera (base de référence) :
DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
  uv run python apps/api/scripts/fleet_reference_daily.py     # (dans le repo, sur chimera)
# 2) export (chimera) :
docker exec pbm-shared-postgres-1 psql -U pbm -d pbm_catalogue_ref \
  -f infra/fleet/export_prices.sql > prices.tsv
# 3) import (PROD, kailo-srv), bundle extrait dans /tmp/pbm-import/ :
sudo -u postgres psql -d pokeboy_prod -f infra/fleet/import_daily.sql

# --- Preuve rapide côté PROD ---
sudo -u postgres psql -d pokeboy_prod -c \
  "select count(*) from card_prices_daily where day = current_date;"
```

## Quand ça casse — runbook

| Symptôme | Cause probable | Quoi faire |
|---|---|---|
| Sonde 09:00 : 0 prix du jour | chimera injoignable la nuit / relevé échoué / import échoué | lire `~/dev/logs/pbm-prices-daily.log` ; relancer `prices-daily.sh` à la main (idempotent) |
| `relevé vide` dans le journal chimera | TCGdex/PTCG en panne réseau | réessayer plus tard ; ne PAS importer un bundle vide (le script refuse déjà) |
| `lignes_sans_carte_en_prod` > 0 à l'import | une extension existe sur chimera mais pas en PROD | lancer d'abord `catalog-weekly.sh` (ajoute les cartes), puis rejouer les prix |
| import PROD : `Permission denied` sur le `\copy` | le user `postgres` ne lit pas le bundle | vérifier `/tmp/pbm-import/` en 755 et les `.tsv` en 644 |
| PROD a rejoué un job lourd | `HEAVY_JOBS_ENABLED` absent/à `true` dans le `.env` PROD | remettre `HEAVY_JOBS_ENABLED=false`, `systemctl restart pokeboy-prod-worker` |
| charge PROD élevée pendant l'import | anormal (l'import est léger) | vérifier qu'aucun cron lourd n'a été réactivé sur le worker (`systemctl cat pokeboy-prod-worker`, `.env`) |

## Ce qui reste manuel / hors périmètre

- La **PROD reste manuelle** pour tout déploiement de code (décision JF).
- L'orchestration launchd vit sur **devAI** (hors dépôt, comme `ai.upgreg.pbm-relais`) ; les pièces
  portables (scripts Python de relève, SQL d'export/import) sont **dans le dépôt** (`apps/api/scripts/`,
  `infra/fleet/`) pour être versionnées et lancées depuis la release déployée.
