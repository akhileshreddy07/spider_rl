"""Every time and size cap in one place."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    move_timeout: float = 0.05       # seconds for one decision
    init_timeout: float = 2.0        # seconds to import the bot and run init (model loading)
    bot_time_budget: float = 0.5     # total decision time per bot per match
    max_strikes: int = 2             # faults tolerated before a bot is disqualified
    max_actions: int = 300           # hard cap on decisions per match
    memory: str = "128m"             # container memory
    max_submission_mb: int = 5       # size of the submission directory

    @property
    def worst_case_match_seconds(self) -> float:
        """Upper bound for a 4-player match: every bot loads slowly and uses its whole budget."""
        return 4 * (self.init_timeout + self.bot_time_budget)


def submission_problems(path: str, limits: Limits) -> list:
    """Reasons a submission directory is unusable (empty list = fine)."""
    if not os.path.isfile(os.path.join(path, "bot.py")):
        return ["missing bot.py"]
    size = sum(os.path.getsize(os.path.join(root, f)) for root, _, files in os.walk(path) for f in files)
    if size > limits.max_submission_mb * 2**20:
        return [f"submission is {size / 2**20:.0f} MB, limit is {limits.max_submission_mb} MB"]
    return []
