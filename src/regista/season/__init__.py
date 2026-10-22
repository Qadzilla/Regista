"""The Regista League: a synthetic season with fixed squads, and player profiles across it (the Scout view's data).

``league``    the league definition (clubs, squads with global player ids, fixtures, seeds); committed as JSON
``build``     regenerates each fixture's match folder from the definition (deterministic, not committed)
``profiles``  per-player aggregates across the season: per-90 rates, percentiles, touch map, moments, evidence
"""
