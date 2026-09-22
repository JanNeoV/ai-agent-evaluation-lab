# Semantic contract versions

Business definitions are frozen before development. A0 exposes correct primitive
fields and joins. A1 adds explicit measures and semantic guidance; it does not alter
the meaning of scheduled, held, unknown, event identity or coverage.

Native rendering is in `platforms/snowflake/deployment.py`. Content hashes enter
Semantic View names, so different versions cannot accidentally share mutable objects.
Portable SemanticSpec and AgentSpec schemas live in `evaluation/schemas/`.

`r1_aggregate_v1.json` is the versioned, platform-neutral semantic contract for the
approved edition aggregate. It defines the one-edition grain, 30 fields, ratio
denominators, NULL policy, calendar-gap interpretation, and P2 CORE claim boundary.
It is data-free and does not implement or render V0-V3; platform rendering remains a
TASK-0007 concern.
