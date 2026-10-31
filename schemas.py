from enum import Enum
from typing import List

class Stage(Enum):
    PLAY = "PLAY"
    PICK_UPGRADE = "PICK_UPGRADE"


class NextRound(Enum):
    UNKNOWN = "UNKNOWN"
    LIVE = "LIVE"
    BLANK = "BLANK"



class UpgradeCounts:
    juice: int
    coffee: int
    mag_glass: int
    pool_floatie: int
    hand_saw: int


class Player:
    health: int
    upgrades: UpgradeCounts
    has_pool_floatie_on: bool

class EjectionStatus:
    blanks_ejected: int
    lives_ejected: int
    unknowns_ejected: int


# given to the bot during its turn in PLAY stage.
class Obs_PLAY:
    max_health: int
    players: List[Player]
    turn: int
    session_no: int

    lives_init: int         # number of live rounds in gun at start of session
    blanks_init: int        # number of blank rounds in gun at start of session
    rounds_remaining: int   # number of rounds remaining in gun
    lives_shot: int         # number of live rounds that have been shot in this session
    blanks_shot: int        # number of blank rounds that have been shot in this  session

    ejections: EjectionStatus

    next_round: NextRound

# given to the bot during its turn in PICK_UPGRADES stage.
class Obs_PICK_UPGRADES:
    max_health: int
    players: List[Player]
    turn: int
    session_no: int

    available_upgrades: UpgradeCounts


class ActionType(Enum):
    SHOOT = "SHOOT"
    USE_UPGRADE = "USE_UPGRADE"


class UpgradeType(Enum):
    JUICE = "JUICE"
    COFFEE = "COFFEE"
    MAG_GLASS = "MAG_GLASS"
    POOL_FLOATIE = "POOL_FLOATIE"
    HAND_SAW = "HAND_SAW"


class Action_PLAY:
    action: ActionType
    useUpgrade: UpgradeType
    target: int | None  # Required if action is USE_UPGRADE POOL_FLOATIE or SHOOT

class Action_PICK_UPGRADES:
    chosen_upgrade: UpgradeType
