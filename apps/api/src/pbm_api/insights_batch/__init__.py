"""Pré-génération par lots des anecdotes et de l'étude en jeu — mission `v4-insights-batch`.

Un seul appel Anthropic par carte (Message Batches API, -50 %) rend ensemble anecdotes
sourcées FR + EN et étude d'utilisation en jeu ; le résultat est écrit dans `card_insights`,
le même cache partagé que consomment déjà les routes à la demande de `v4-anecdotes`/`v4-jeu`
(`pbm_api.insights.service`/`pbm_api.ingame.service`) — elles ne rappellent l'IA que pour une
carte que ce lot n'a pas encore couverte.
"""
