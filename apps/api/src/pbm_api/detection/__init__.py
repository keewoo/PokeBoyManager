"""Détection et découpage des cartes d'une photo (mission `v3-detection`).

Pipeline : contours OpenCV (ratio 63×88 mm) + redressement perspective ; repli par boîtes
englobantes demandées au LLM vision quand la photo est difficile (pochettes, reflets, fond
clair), affinées ensuite par OpenCV dans chaque boîte. Voir `pbm_api.detection.pipeline`.
"""
