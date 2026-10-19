#!/usr/bin/env python
"""Preuve de mise en ligne du jeu : une partie **réellement jouée** contre le serveur LIVE.

Pourquoi ce script est versionné : chaque livraison du jeu devait prouver qu'une partie se joue en
production, et chaque livraison réécrivait son script de preuve dans le venv déployé — perdu
ensuite. Comme les scripts de livraison partis avec ``/tmp`` (19/10/2026), un outil de preuve qui
ne survit pas à la livraison oblige à le refaire. Celui-ci reste.

Il emprunte le chemin réel d'un joueur — ``https://pokeboy.lol/api``, donc Caddy puis l'uvicorn
qui sert vraiment — et peut donc tourner depuis n'importe quel poste de la flotte. Viser
``127.0.0.1:8100`` ne marche pas : le cookie de session est ``Secure``, il n'est pas renvoyé sur du
HTTP en clair. ``PBM_BASE`` permet de pointer un autre environnement. Rien n'est rejoué côté client :
le serveur fait autorité, on lit ``actions.legales`` de ``GET /games/{id}/state`` et on joue ce
qu'il déclare jouable. Si le moteur change ses étiquettes, ce script suit.

Prérequis : ``scripts/seed_partie_e2e.py`` a semé les deux comptes et leurs decks (A attaque à 60,
B a un seul Pokémon à 110 PV sans attaque : deux attaques et son banc vide donnent la deuxième voie
de victoire de **R-14.1**, une vraie fin de partie, pas un abandon).

    .venv/bin/python scripts/prouver_partie_prod.py <email_a> <email_b> <mot_de_passe> <deck_a> <deck_b>

Codes de sortie : ``0`` partie jouée et gagnée dans les règles, ``1`` la preuve a échoué (et dit
pourquoi). Aucun secret affiché.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

# Le chemin RÉEL d'un joueur : HTTPS, Caddy, préfixe `/api`. On ne vise pas l'uvicorn en
# 127.0.0.1 — le cookie de session est `Secure`, il n'est pas renvoyé sur du HTTP en clair, et
# viser le port interne reviendrait à prouver un chemin que personne n'emprunte.
BASE = os.environ.get("PBM_BASE", "https://pokeboy.lol/api").rstrip("/")
COUPS_MAX = 160  # très au-dessus des 32 coups mesurés, mais borné : jamais de boucle folle
REFUS_MAX = 12   # un conflit de numéro à la mise en place est légitime ; au-delà, on échoue


class Joueur:
    """Une session HTTP authentifiée : cookie de session, jeton CSRF, et rien d'autre."""

    def __init__(self, nom: str, email: str, mot_de_passe: str) -> None:
        self.nom = nom
        self.email = email
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        self._connecter(mot_de_passe)

    def _csrf(self) -> str:
        for c in self.cookies:
            if c.name == "pbm_csrf":
                return c.value
        raise RuntimeError(f"{self.nom} : aucun cookie CSRF après connexion")

    def _appel(
        self, methode: str, chemin: str, corps: dict | None = None, avec_csrf: bool = True
    ) -> tuple[int, object]:
        donnees = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(BASE + chemin, data=donnees, method=methode)
        req.add_header("Content-Type", "application/json")
        req.add_header("Origin", "https://pokeboy.lol")
        # Le login est la seule écriture sans session : il n'y a pas encore de jeton CSRF à
        # présenter. Partout ailleurs le jeton est exigé, et son absence ferait un 403 bien visible.
        if methode != "GET" and avec_csrf:
            req.add_header("X-CSRF-Token", self._csrf())
        try:
            with self.opener.open(req, timeout=30) as r:
                brut = r.read().decode()
                return r.status, (json.loads(brut) if brut else None)
        except urllib.error.HTTPError as e:
            brut = e.read().decode()
            try:
                return e.code, json.loads(brut)
            except json.JSONDecodeError:
                return e.code, brut

    def _connecter(self, mot_de_passe: str) -> None:
        code, rep = self._appel(
            "POST", "/auth/login", {"email": self.email, "password": mot_de_passe}, avec_csrf=False
        )
        if code != 200:
            raise RuntimeError(f"{self.nom} : connexion refusée ({code}) — {rep}")

    def get(self, chemin: str) -> tuple[int, object]:
        return self._appel("GET", chemin)

    def post(self, chemin: str, corps: dict) -> tuple[int, object]:
        return self._appel("POST", chemin, corps)


def autoritaire(reponse: dict) -> dict:
    """La vue autoritaire du joueur. Le serveur l'imbrique sous ``vue`` ; une autre forme est une panne."""
    vue = reponse.get("vue")
    if not isinstance(vue, dict):
        raise RuntimeError("la réponse ne porte pas « vue » — clés : " + ", ".join(sorted(reponse)))
    return vue


def legales(reponse: dict) -> list[dict]:
    """Les coups que le SERVEUR déclare jouables. Une forme inattendue est une panne, pas un vide."""
    vue = autoritaire(reponse)
    if "actions_legales" not in vue:
        raise RuntimeError(
            "la vue ne porte pas « actions_legales » — clés : " + ", ".join(sorted(vue))
        )
    return vue["actions_legales"]


def terminee(reponse: dict) -> tuple[bool, str]:
    """La partie est-elle finie, et comment ? ``terminee``, ``vainqueur`` et ``raison_fin`` du serveur."""
    vue = autoritaire(reponse)
    if not vue.get("terminee"):
        return False, ""
    return True, f"vainqueur={vue.get('vainqueur')} raison={vue.get('raison_fin')}"


# L'abandon est TOUJOURS légal : un pilote qui joue « le premier coup légal » abandonne au
# premier tour et croit avoir prouvé quelque chose (vécu le 19/10/2026 : partie « terminée » en
# 4 coups, raison=abandon). La preuve attendue est une vraie fin de partie — K.O. puis banc vide,
# deuxième voie de **R-14.1**. On exclut donc l'abandon, et on préfère ce qui fait avancer la
# partie : frapper d'abord, se préparer à frapper ensuite.
JAMAIS = ("abandonner",)
# ⚠️ Le type d'action est « declarer_attaque ». « attaquer » est le nom de la FAMILLE dans
# `pbm_game.actions.familles_jeu`, pas celui du coup : un pilote qui attend « attaquer » joue une
# partie entière sans jamais frapper, et finit par épuisement de pioche en croyant avoir prouvé le
# combat (vécu le 19/10/2026 : 82 coups, zéro attaque).
PREFERENCE = (
    "declarer_attaque",
    "repondre_demande",
    "attacher_energie",
    "placer_mise_en_place",
    "poser",
    "promouvoir",
    "evoluer",
    "jouer_objet",
    "jouer_supporter",
    "avancer_phase",
)


def choisir(jouables: list[dict]) -> dict | None:
    """Le coup à jouer parmi ceux que le serveur déclare légaux, l'abandon mis à part."""
    utiles = [c for c in jouables if c["type"] not in JAMAIS]
    if not utiles:
        return None
    for type_ in PREFERENCE:
        for c in utiles:
            if c["type"] == type_:
                return c
    return utiles[0]


def _partie_en_cours(j: "Joueur") -> str | None:
    """L'identifiant d'une partie active de ce joueur, s'il en a une (sinon ``None``)."""
    code, rep = j.get("/games")
    if code != 200 or not isinstance(rep, list):
        return None
    for g in rep:
        # Statuts du modèle : « en_cours », « terminee », « expiree ».
        if isinstance(g, dict) and g.get("status") == "en_cours" and g.get("id"):
            return str(g["id"])
    return None


def main() -> int:
    if len(sys.argv) != 6:
        print(__doc__)
        return 1
    email_a, email_b, mdp, deck_a, deck_b = sys.argv[1:6]

    a = Joueur("A", email_a, mdp)
    b = Joueur("B", email_b, mdp)
    print("connexion des deux comptes : OK")

    # Jouabilité des decks : le bouton « Entrer dans la file » en dépend, autant le prouver ici.
    for j, deck in ((a, deck_a), (b, deck_b)):
        code, rep = j.get(f"/matchmaking/decks/{deck}/jouabilite")
        jouable = isinstance(rep, dict) and rep.get("jouable")
        print(f"jouabilité deck {j.nom} : {code} jouable={jouable}")
        if code != 200 or not jouable:
            print(f"⛔ deck de {j.nom} non jouable — {rep}")
            return 1

    # Appariement : A entre dans la file, B l'y rejoint et la partie est créée. Un 409
    # « déjà en partie » n'est pas un échec : c'est une partie d'une exécution précédente, et on
    # la reprend plutôt que d'en abandonner une à chaque essai.
    game_id = _partie_en_cours(a)
    if game_id:
        print(f"partie déjà en cours, on la reprend : {game_id}")
    else:
        code, rep = a.post("/matchmaking/queue", {"deck_id": deck_a})
        print(f"A entre dans la file : {code} {str(rep)[:160]}")
        if code not in (200, 409):
            return 1
        code, rep = b.post("/matchmaking/queue", {"deck_id": deck_b})
        print(f"B entre dans la file : {code} {str(rep)[:160]}")
        if code != 200 or not isinstance(rep, dict) or rep.get("status") != "apparie":
            print(f"⛔ pas d'appariement — {rep}")
            return 1
        game_id = rep["game_id"]
        print(f"partie créée : {game_id}")

    coups = refus = 0
    familles: dict[str, int] = {}
    while coups < COUPS_MAX:
        progresse = False
        for j in (a, b):
            code, vue = j.get(f"/games/{game_id}/state")
            if code != 200:
                print(f"⛔ état illisible pour {j.nom} : {code} {vue}")
                return 1
            assert isinstance(vue, dict)
            fini, comment = terminee(vue)
            if fini:
                print(f"partie TERMINÉE après {coups} coups — {comment}")
                code, bilan = j.get(f"/games/{game_id}/bilan")
                print(f"bilan ({j.nom}) : {code} {json.dumps(bilan, ensure_ascii=False)[:400]}")
                print(f"familles de coups jouées : {familles}")
                return 0
            jouables = legales(vue)
            coup = choisir(jouables)
            if coup is None:
                continue
            code, rep = j.post(
                f"/games/{game_id}/actions",
                {"type": coup["type"], "params": coup["params"], "numero_attendu": vue.get("numero")},
            )
            if code == 200:
                coups += 1
                progresse = True
                familles[coup["type"]] = familles.get(coup["type"], 0) + 1
            else:
                refus += 1
                print(f"refus {refus} ({j.nom}, {coup['type']}) : {code} {str(rep)[:160]}")
                if refus > REFUS_MAX:
                    print("⛔ trop de refus — les coups ne passent plus")
                    return 1
        if not progresse:
            print("⛔ aucun des deux joueurs n'a de coup jouable et la partie n'est pas finie")
            return 1

    print(f"⛔ {COUPS_MAX} coups sans fin de partie — borne atteinte")
    return 1


if __name__ == "__main__":
    sys.exit(main())
