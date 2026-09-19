"""Écrit le schéma OpenAPI de l'API sur stdout, sans lancer de serveur."""

import json
import sys

from pbm_api.main import app

json.dump(app.openapi(), sys.stdout)
