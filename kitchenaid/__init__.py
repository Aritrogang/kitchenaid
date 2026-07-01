"""kitchenaid — a kitchen agent that adapts to your profile, tastes, and the moment.

Phase 1: a single agent that does profile -> suggest a meal -> check constraints inline.
The deterministic gate lives in `tools.py` and is called inline by `agent.py`; Phase 2
moves it behind the Dietitian agent unchanged.
"""

__version__ = "0.1.0"
