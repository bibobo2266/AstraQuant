# Scalable Research Funnel

AstraQuant should not run every idea through the full portfolio simulator.

The scalable path is:

1. Feature layer — compute PIT-safe research features once.
2. Batch candidate screen — evaluate tens or hundreds of multi-feature recipes using cached same-day cross-sectional ranks and a fixed forward outcome.
3. Redundancy / stability review — keep adverse evidence; reject weak, unstable, or redundant recipes without portfolio simulation.
4. Portfolio attribution — only a small surviving set pays the cost of RAW execution, capacity, settlement, CA accounting, FIFO reconstruction, and falsification.
5. Locked OOS — only explicitly frozen candidates may enter.

The batch_screen function in astraquant.research.batch_screen is the cheap second-stage engine. A recipe is a weighted stack of feature terms; it is not restricted to one indicator. Feature ranks are computed once per date and reused across recipes, so 100+ recipes do not require 100 independent data/execution pipelines.

This screen is not promotion evidence. It intentionally excludes portfolio sequencing, capacity, execution costs, and locked OOS. Its job is to cheaply kill weak hypotheses before they consume expensive simulation time.

equal_weight_combinations can generate recipe families automatically. For example, 15 features taken two at a time produce 105 recipes in one batch. Recipe generation must still be declared before inspecting the resulting ranking; do not generate new combinations in response to observed winners.
