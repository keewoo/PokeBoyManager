"""Decks : création, légalité et sauvegarde (lot `v7-decks-api`).

Un deck ne référence que le catalogue (`deck_cards.card_id`) ; la contrainte « uniquement avec
ses cartes » et la règle des 60/4 sont un contrôle de légalité recalculé à la lecture
(`legality`), jamais mémorisé — voir `pbm_api.models.decks`.
"""
