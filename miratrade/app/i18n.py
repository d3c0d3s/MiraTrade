"""Kept so nothing in the desktop package has to change while it still exists.

The catalogue moved to :mod:`miratrade.i18n`, in the core, when the web became a replacement for
this app rather than a companion to it: the web cannot import from here (``docs/ESTRUCTURA.md``),
and a second copy of the Spanish would have drifted from the first within a week.
"""
from miratrade.i18n import CATALOGS, DEFAULT, ES, LANGUAGES, language, set_language, t

__all__ = ["CATALOGS", "DEFAULT", "ES", "LANGUAGES", "language", "set_language", "t"]
