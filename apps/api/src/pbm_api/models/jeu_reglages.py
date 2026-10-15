"""Les réglages **globaux** du jeu — ceux que JF pose sur le serveur, pas ceux d'un joueur (lot
`j-classement-prive`, jalon J4, DJ6).

Il existait déjà des réglages *par compte* (`jeu_confort`, `jeu_emotes`, `jeu_rendu`,
`notification_reglages`) : ils appartiennent au joueur, qui les change depuis son écran. Ce qui
manquait, c'est l'autre moitié : un réglage **de produit**, décidé par JF pour tout le monde.

DJ6 l'exige explicitement — « classement privé et badges en option, **activables par JF** ». Deux
voies étaient possibles, et le choix n'est pas cosmétique :

* une **variable d'environnement** : il faut alors éditer le fichier d'environnement du serveur et
  **redémarrer les conteneurs** pour qu'elle soit lue. C'est une intervention de livraison, et le
  critère d'acceptation du lot dit l'inverse (« la désactivation est un réglage, pas un
  déploiement ») ;
* une **ligne en base**, lue à chaque requête : une commande d'administration suffit, le serveur
  continue de tourner, et l'effet est immédiat. C'est ce qui est retenu ici.

Le vocabulaire (quelles clés existent, quelles valeurs sont acceptées, quel est le défaut) vit dans
:mod:`pbm_api.jeu.reglages` — **pas** dans cette table. Une clé inconnue est donc refusée par le
code avant d'arriver ici : la base ne porte que ce que le produit déclare, et une faute de frappe
dans une commande d'administration ne fabrique pas un réglage fantôme que personne ne lit.

⚠️ Cette table ne porte **aucune donnée personnelle** : ni ``user_id``, ni rien qui s'y rapporte.
C'est voulu — elle échappe donc à l'export et à l'effacement RGPD, qui n'ont rien à y effacer.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class JeuReglage(Base, TimestampMixin):
    """Un réglage global du jeu : une clé déclarée, sa valeur, et la date du dernier changement.

    Clé/valeur plutôt qu'une colonne par réglage, pour une raison précise : ajouter un réglage ne
    doit pas coûter une **migration**. DJ6 en annonce déjà un second (les badges, lot
    `j-profil-jeu`) et le jeu en aura d'autres ; une table à colonnes obligerait chaque lot aval à
    migrer la base pour un booléen.

    Le prix habituel de ce motif — « n'importe qui écrit n'importe quoi » — est payé ailleurs :
    :data:`pbm_api.jeu.reglages.REGLAGES` déclare les clés et leurs valeurs possibles, et
    :func:`pbm_api.jeu.reglages.valider` refuse tout le reste. Une ligne dont la clé n'est pas
    déclarée ne peut donc pas naître par le chemin normal, et si elle existait quand même (écriture
    SQL à la main), la lecture l'ignore et rend le défaut — jamais une valeur inventée.

    ``absente`` n'est pas un cas d'erreur : un réglage jamais touché n'a pas de ligne, et la lecture
    rend son défaut déclaré. C'est pourquoi l'installation d'un serveur n'a rien à semer.
    """

    __tablename__ = "jeu_reglages"

    #: La clé du réglage, telle que déclarée dans :data:`pbm_api.jeu.reglages.REGLAGES`.
    cle: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: La valeur, toujours stockée en texte : le sens (booléen, nom de barème) est donné par la
    #: déclaration de la clé, pas par le type SQL. Une colonne par type serait trois colonnes
    #: nullables, donc trois façons de se contredire.
    valeur: Mapped[str] = mapped_column(String(64), nullable=False)


__all__ = ["JeuReglage"]
