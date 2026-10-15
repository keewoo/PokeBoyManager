"""Point d'entrée FastAPI : construit l'app, pose les middlewares et monte tous les routeurs."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pbm_api.config import settings
from pbm_api.routers.ai_keys import router as ai_keys_router
from pbm_api.routers.auth import router as auth_router
from pbm_api.routers.card_insights import router as card_insights_router
from pbm_api.routers.cards import router as cards_router
from pbm_api.routers.catalog import router as catalog_router
from pbm_api.routers.classement import router as classement_router
from pbm_api.routers.collection import router as collection_router
from pbm_api.routers.dashboard import router as dashboard_router
from pbm_api.routers.decks import router as decks_router
from pbm_api.routers.detections import router as detections_router
from pbm_api.routers.export import router as export_router
from pbm_api.routers.games import router as games_router
from pbm_api.routers.games_ws import router as games_ws_router
from pbm_api.routers.health import router as health_router
from pbm_api.routers.images import router as images_router
from pbm_api.routers.imports import router as imports_router
from pbm_api.routers.in_game_study import router as in_game_study_router
from pbm_api.routers.invitations import router as invitations_router
from pbm_api.routers.jeu_confort import router as jeu_confort_router
from pbm_api.routers.jeu_demandes import router as jeu_demandes_router
from pbm_api.routers.jeu_emotes import router as jeu_emotes_router
from pbm_api.routers.jeu_rendu import router as jeu_rendu_router
from pbm_api.routers.lancement import router as lancement_router
from pbm_api.routers.matchmaking import router as matchmaking_router
from pbm_api.routers.notifications import router as notifications_router
from pbm_api.routers.observabilite import router as observabilite_router
from pbm_api.routers.profil_jeu import router as profil_jeu_router
from pbm_api.routers.profile import router as profile_router
from pbm_api.routers.stats_joueur import router as stats_joueur_router
from pbm_api.routers.uploads import router as uploads_router
from pbm_api.routers.wishlist import router as wishlist_router
from pbm_api.security.headers import SecurityHeadersMiddleware
from pbm_api.security.log_filter import install_api_key_redaction, install_secret_url_redaction
from pbm_api.security.validation_errors import install_validation_error_redaction

install_api_key_redaction()
install_secret_url_redaction()

app = FastAPI(title="PokeBoyManager API")
install_validation_error_redaction(app)
app.add_middleware(SecurityHeadersMiddleware)

# `apps/web` et `apps/api` sont deux origines distinctes (ports différents en local, sous-
# domaines distincts en UAT/PROD) : sans CORS, le navigateur bloque tout fetch, y compris les
# routes d'authentification. `allow_credentials` est nécessaire pour que le cookie de session
# parte avec la requête ; il impose une liste d'origines explicite (jamais `*`).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_public_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(images_router)
app.include_router(ai_keys_router)
app.include_router(catalog_router)
app.include_router(profile_router)
app.include_router(uploads_router)
app.include_router(detections_router)
app.include_router(collection_router)
app.include_router(decks_router)
app.include_router(dashboard_router)
app.include_router(card_insights_router)
app.include_router(export_router)
app.include_router(in_game_study_router)
app.include_router(cards_router)
app.include_router(wishlist_router)
app.include_router(imports_router)
app.include_router(games_router)
# Canal temps réel des parties (WebSocket + repli HTTP `/games/{id}/sync`) : même préfixe `/games`,
# routeur distinct (lot `j-temps-reel`).
app.include_router(games_ws_router)
app.include_router(matchmaking_router)
app.include_router(invitations_router)
app.include_router(lancement_router)
app.include_router(jeu_demandes_router)
# Notifications du jeu (lot `j-notifications-jeu`) : le canal dans l'application et ses reglages.
# Aucune route n'EMET de notification — elles naissent d'un evenement du jeu, jamais d'un client.
app.include_router(notifications_router)
# Rendu des cartes en jeu (lot `j-rendu-carte`) : reglages DJ5, apercu de deck, photos servies
# dans le cadre d'une partie.
app.include_router(jeu_rendu_router)
# Confort et accessibilite du jeu (lot `j-accessibilite-jeu`) : animations, taille du texte, et le
# temps rallonge (DJ4) — lu au LANCEMENT d'une partie, jamais pendant (les horloges sont figees).
app.include_router(jeu_confort_router)
# Emotes en jeu (lot `j-echanges-emotes`, DJ10) : le catalogue ferme et l'interrupteur « j'echange
# des emotes ». L'envoi, lui, n'a aucune route : il passe par le canal temps reel.
app.include_router(jeu_emotes_router)
# Classement prive entre comptes invites (lot `j-classement-prive`, DJ6) : une seule route, en
# lecture. L'interrupteur et le bareme sont des REGLAGES poses par JF en ligne de commande
# (`python -m pbm_api.admin set-reglage-jeu`) — eteint par defaut, et aucune route ne les ecrit.
app.include_router(classement_router)
# Supervision du jeu (lot `j-observabilite-jeu`) : les metriques lisibles sans SSH, reservees
# aux comptes ayant l'acces au jeu (D11) — agregees, jamais ventilees par compte.
app.include_router(observabilite_router)
# Mes parties : historique et statistiques du joueur (lot `j-stats-joueur`, jalon J4). Deux routes
# en LECTURE seulement — rien n'est stocke, tout est recalcule depuis `game_result_players` a
# chaque appel, comme le classement prive. Il n'y a donc aucun agregat a reparer, et aucune route
# d'ecriture a garder.
app.include_router(stats_joueur_router)
# Profil de joueur : vitrine, carte fetiche, badges (lot `j-profil-jeu`, jalon J4, DJ6). La
# vitrine des badges est ETEINTE par defaut — JF l'allume par `set-reglage-jeu badges_actifs oui`,
# sans redeployer. L'attribution, elle, tourne a chaque cloture : un badge qui depend du journal ne
# se rattrape pas apres la purge.
app.include_router(profil_jeu_router)
