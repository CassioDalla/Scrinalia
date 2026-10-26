"""The evaluation of the AI against the institution's own decisions (ADR 0018).

Two things live here and nowhere else: the metric the bench and the operations panel share, and the
trial executor that measures a configuration without writing archival content. The heavy imports
(the engine registry) stay inside the trial module, so the API can read the metric without loading a
model.
"""
