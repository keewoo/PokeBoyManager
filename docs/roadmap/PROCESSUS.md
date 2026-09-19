# Processus de suivi

1. **Le plan** (`roadmap.json`) décrit chaque lot : dates, couloir (machine), dépendances, décision de JF,
   mission, livrables, tâches sans objet. On le modifie à la main, puis `python3 docs/roadmap/suivi.py build`.
   Le build **refuse** un plan incohérent (dépendance qui finit après le début, couloir qui porte deux lots
   en même temps, lot qui commence avant sa décision).
2. **Lancer un lot** : copier son prompt (page ROADMAP, bouton « Copier le prompt », ou `prompts/<id>.md`)
   dans Claude Code. Sur la machine du couloir, la session exécute ; ailleurs, elle pilote.
3. **Garde-fou** : `suivi.py verifier <id>` — code 2 si une dépendance n'est pas livrée ou si la décision
   n'est pas prise. Seul JF lève un blocage.
4. **Pendant le lot** : `suivi.py tache <id> <tache> <etat> "<preuve>"` à chaque étape.
5. **Clôture, quelle que soit l'issue** : `suivi.py compte-rendu`, `suivi.py statut`, `suivi.py build`,
   commit ciblé, PR, republication de la page.
6. **Décisions** : `suivi.py decision D3 "<texte exact de JF>"`.

Statuts : `a_faire` → `en_cours` → (`attente_validation` | `bloque`) → `livre_uat` → `attente_go_prod` → `livre`.
