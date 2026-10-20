"""Regista: every touch, every replay, every player, found instantly.

Package layout:
- ``regista.schema``  load and validate the event and clip streams against data/synthetic/schema
- ``regista.synth``   synthetic match generator (football-realistic events with no footage)
- ``regista.clips``   the clip rule and labelling (intelligence layer reference implementation)
"""

from regista.schema import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION"]
__version__ = "0.1.0"
