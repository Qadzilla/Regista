"""Regista Studio, the control room, behind the HTTP routes in ``regista.studio_api``.

facts.py   read-only facts about this replica: pipeline runs, the to-do list, the render cache, Cosmos DB and Search counts
jobs.py    local-only vision jobs (one subprocess at a time, an allow-listed argument set, logs under data/studio/jobs/)
__main__   ``python3 -m regista.studio status [--url URL]``: the overview, for Claude at the start of a session
"""
