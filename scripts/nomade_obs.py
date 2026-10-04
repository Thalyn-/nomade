"""Connexion à obs-websocket partagée par les scripts Nomade.

Les versions récentes d'obsws_python n'acceptent que des arguments nommés :
tous les scripts passent donc par ``creer_client``.
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Callable

HOTE_PAR_DEFAUT = "127.0.0.1"
PORT_PAR_DEFAUT = 4455
DELAI_PAR_DEFAUT = 3

# Catégories renvoyées par ``classer_erreur``.
INJOIGNABLE = "injoignable"
MOT_DE_PASSE = "mot_de_passe"
REQUETE = "requete"
INTERNE = "interne"


def creer_client(
    hote: str = HOTE_PAR_DEFAUT,
    port: int = PORT_PAR_DEFAUT,
    mot_de_passe: str | None = None,
    delai: float = DELAI_PAR_DEFAUT,
    fabrique: Callable[..., Any] | None = None,
) -> Any:
    """Crée un ``ReqClient`` avec des arguments nommés uniquement."""
    if fabrique is None:
        from obsws_python import ReqClient as fabrique
    if mot_de_passe is None:
        mot_de_passe = os.environ.get("OBS_MDP", "")
    return fabrique(host=hote, port=port, password=mot_de_passe, timeout=delai)


def code_erreur_obs(erreur: BaseException) -> int | None:
    """Extrait le code de réponse OBS (ex. 605) d'une erreur de requête."""
    code = getattr(erreur, "code", None)
    if isinstance(code, int):
        return code
    correspondance = re.search(r"returned code (\d+)", str(erreur))
    return int(correspondance.group(1)) if correspondance else None


def classer_erreur(erreur: BaseException) -> tuple[str, str]:
    """Classe une erreur en (catégorie, détail) sans jamais citer le mot de passe."""
    detail = f"{type(erreur).__name__}: {erreur}"
    message = str(erreur).lower()
    if code_erreur_obs(erreur) is not None:
        return REQUETE, detail
    if isinstance(erreur, TypeError):
        return INTERNE, detail
    if "auth" in message or "password" in message:
        return MOT_DE_PASSE, detail
    if isinstance(erreur, (ConnectionError, TimeoutError, OSError)) or any(
        indice in message
        for indice in ("refused", "timed out", "timeout", "unreachable", "end of file", "eof")
    ):
        return INJOIGNABLE, detail
    return INTERNE, detail


def fermer_client(client: Any) -> None:
    """Ferme proprement une connexion, sans jamais lever d'erreur."""
    if client is None:
        return
    try:
        client.disconnect()
    except Exception:
        pass


class ConnexionOBS:
    """Connexion persistante avec reconnexion à délai croissant."""

    def __init__(
        self,
        hote: str = HOTE_PAR_DEFAUT,
        port: int = PORT_PAR_DEFAUT,
        fabrique: Callable[..., Any] | None = None,
        horloge: Callable[[], float] = time.monotonic,
        delai_initial: float = 2.0,
        delai_maximal: float = 30.0,
    ) -> None:
        self.hote = hote
        self.port = port
        self._fabrique = fabrique
        self._horloge = horloge
        self._delai_initial = delai_initial
        self._delai_maximal = delai_maximal
        self._client: Any = None
        self._delai = delai_initial
        self._prochaine_tentative = 0.0
        self._derniere_erreur: BaseException | None = None
        self._verrou = threading.RLock()

    def obtenir(self) -> Any:
        """Retourne le client ouvert ; se reconnecte si besoin, avec un délai croissant."""
        with self._verrou:
            if self._client is not None:
                return self._client
            if self._derniere_erreur is not None and self._horloge() < self._prochaine_tentative:
                raise self._derniere_erreur
            try:
                self._client = creer_client(self.hote, self.port, fabrique=self._fabrique)
            except Exception as erreur:
                self._derniere_erreur = erreur
                self._prochaine_tentative = self._horloge() + self._delai
                self._delai = min(self._delai * 2, self._delai_maximal)
                raise
            self._derniere_erreur = None
            self._delai = self._delai_initial
            return self._client

    def invalider(self) -> None:
        """Abandonne la connexion courante (erreur pendant l'utilisation)."""
        with self._verrou:
            fermer_client(self._client)
            self._client = None

    def reinitialiser(self) -> None:
        """Ferme la connexion et autorise une reconnexion immédiate (ex. nouveau mot de passe)."""
        with self._verrou:
            self.invalider()
            self._derniere_erreur = None
            self._delai = self._delai_initial
            self._prochaine_tentative = 0.0

    def fermer(self) -> None:
        self.reinitialiser()

