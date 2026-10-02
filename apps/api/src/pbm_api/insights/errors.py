"""Erreurs propres à la génération d'anecdotes — levées par `pbm_api.insights.service`."""


class NoAiKeyConfiguredError(Exception):
    """L'utilisateur n'a aucun fournisseur IA par défaut avec une clé enregistrée (D4) — la
    génération d'anecdotes reste désactivée tant qu'il n'en choisit pas un dans son profil."""
