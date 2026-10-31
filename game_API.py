import random
from typing import List

from schemas import *

# Tracks the entire game
class GameState:
    max_health: int
    players: List[Player]
    alive_players: int
    stage: Stage
    turn: int
    session_no: int

    # PLAY stage fields
    round_contents: List[bool]  # order of all rounds in this session. Only changes in new session.
    lives_init: int | None      # number of live rounds in gun at start of session
    blanks_init: int | None     # number of blank rounds in gun at start of session
    rounds_remaining: int       # number of rounds remaining in gun
    lives_shot: int | None      # number of live rounds that have been shot in this session
    blanks_shot: int | None     # number of blank rounds that have been shot in this  session
    damage: int | None          # damage dealt by next round. Increased by 1 when hand saw is used.
    player_ejection_view: List[EjectionStatus]  # count of ejections as seen by each player

    # PICK_UPGRADE stage fields
    available_upgrades: UpgradeCounts | None
    player_next_round_view: NextRound
    rng: random.Random
    game_over: bool
    elimination_order: List[int]  # player indices in the order they died


def _new_upgrade_counts() -> UpgradeCounts:
    counts = UpgradeCounts()
    counts.juice = 0
    counts.coffee = 0
    counts.mag_glass = 0
    counts.pool_floatie = 0
    counts.hand_saw = 0
    return counts


def _copy_upgrade_counts(source: UpgradeCounts) -> UpgradeCounts:
    counts = _new_upgrade_counts()
    counts.juice = source.juice
    counts.coffee = source.coffee
    counts.mag_glass = source.mag_glass
    counts.pool_floatie = source.pool_floatie
    counts.hand_saw = source.hand_saw
    return counts


def _copy_player(source: Player) -> Player:
    player = Player()
    player.health = source.health
    player.upgrades = _copy_upgrade_counts(source.upgrades)
    player.has_pool_floatie_on = source.has_pool_floatie_on
    return player


def _copy_ejection_status(source: EjectionStatus) -> EjectionStatus:
    status = EjectionStatus()
    status.blanks_ejected = source.blanks_ejected
    status.lives_ejected = source.lives_ejected
    status.unknowns_ejected = source.unknowns_ejected
    return status


def _new_ejection_status() -> EjectionStatus:
    status = EjectionStatus()
    status.blanks_ejected = 0
    status.lives_ejected = 0
    status.unknowns_ejected = 0
    return status


def _setup_round(state: GameState) -> None:
    shell_count = 2 * (state.session_no + 1) * state.alive_players
    min_live = shell_count // 4
    max_live = shell_count * 4 // 5
    live_count = state.rng.randint(min_live, max_live)
    blank_count = shell_count - live_count

    contents: List[bool] = []
    remaining_live = live_count
    remaining_blank = blank_count
    for _ in range(shell_count):
        if remaining_live and remaining_blank:
            if state.rng.randrange(2):
                contents.append(True)
                remaining_live -= 1
            else:
                contents.append(False)
                remaining_blank -= 1
        elif remaining_live:
            contents.append(True)
            remaining_live -= 1
        else:
            contents.append(False)
            remaining_blank -= 1

    state.round_contents = contents
    state.lives_init = live_count
    state.blanks_init = blank_count
    state.rounds_remaining = shell_count
    state.lives_shot = 0
    state.blanks_shot = 0
    state.damage = 1
    state.player_ejection_view = [_new_ejection_status() for _ in state.players]
    state.player_next_round_view = NextRound.UNKNOWN
    state.available_upgrades = None


def _advance_turn(state: GameState, from_turn: int, skip_floaties: bool) -> int:
    player_count = len(state.players)
    for offset in range(1, player_count + 1):
        candidate = (from_turn + offset) % player_count
        if state.players[candidate].health <= 0:
            continue
        if skip_floaties and state.players[candidate].has_pool_floatie_on:
            state.players[candidate].has_pool_floatie_on = False
            continue
        return candidate
    return from_turn


def _generate_upgrades(state: GameState) -> UpgradeCounts:
    alive_count = state.alive_players
    upgrade_count = min(3 * (state.session_no + 1) * alive_count, 15 * alive_count)
    available_types = [UpgradeType.JUICE, UpgradeType.COFFEE, UpgradeType.MAG_GLASS]
    if state.session_no >= 1:
        available_types.extend([UpgradeType.POOL_FLOATIE, UpgradeType.HAND_SAW])

    counts = _new_upgrade_counts()
    count_by_type = {
        UpgradeType.JUICE: "juice",
        UpgradeType.COFFEE: "coffee",
        UpgradeType.MAG_GLASS: "mag_glass",
        UpgradeType.POOL_FLOATIE: "pool_floatie",
        UpgradeType.HAND_SAW: "hand_saw",
    }
    for _ in range(upgrade_count):
        attribute = count_by_type[state.rng.choice(available_types)]
        setattr(counts, attribute, getattr(counts, attribute) + 1)
    return counts


def _start_upgrade_stage(state: GameState, ending_turn: int) -> None:
    state.turn = _advance_turn(state, ending_turn, skip_floaties=True)
    state.stage = Stage.PICK_UPGRADE
    state.available_upgrades = _generate_upgrades(state)


def _consume_next_shell(state: GameState) -> bool:
    shell_index = len(state.round_contents) - state.rounds_remaining
    is_live = state.round_contents[shell_index]
    state.rounds_remaining -= 1
    state.player_next_round_view = NextRound.UNKNOWN
    return is_live


def _play_observation(state: GameState) -> Obs_PLAY:
    observation = Obs_PLAY()
    observation.max_health = state.max_health
    observation.players = [_copy_player(player) for player in state.players]
    observation.turn = state.turn
    observation.session_no = state.session_no
    observation.lives_init = state.lives_init
    observation.blanks_init = state.blanks_init
    observation.rounds_remaining = state.rounds_remaining
    observation.lives_shot = state.lives_shot
    observation.blanks_shot = state.blanks_shot
    observation.ejections = _copy_ejection_status(state.player_ejection_view[state.turn])
    observation.next_round = state.player_next_round_view
    return observation


def _upgrade_observation(state: GameState) -> Obs_PICK_UPGRADES:
    observation = Obs_PICK_UPGRADES()
    observation.max_health = state.max_health
    observation.players = [_copy_player(player) for player in state.players]
    observation.turn = state.turn
    observation.session_no = state.session_no
    observation.available_upgrades = _copy_upgrade_counts(
        state.available_upgrades if state.available_upgrades is not None else _new_upgrade_counts()
    )
    return observation


def _use_upgrade(state: GameState, upgrade_type: UpgradeType, target: int | None) -> bool:
    player_index = state.turn
    player = state.players[player_index]
    inventory_attribute = {
        UpgradeType.JUICE: "juice",
        UpgradeType.COFFEE: "coffee",
        UpgradeType.MAG_GLASS: "mag_glass",
        UpgradeType.POOL_FLOATIE: "pool_floatie",
        UpgradeType.HAND_SAW: "hand_saw",
    }.get(upgrade_type)
    if inventory_attribute is None:
        raise ValueError("Unknown upgrade type")
    if getattr(player.upgrades, inventory_attribute) <= 0:
        raise ValueError("Player does not have that upgrade")

    if upgrade_type == UpgradeType.POOL_FLOATIE:
        if target is None or target == player_index or state.players[target].health <= 0:
            raise ValueError("Pool floatie requires a different living target")
        if state.players[target].has_pool_floatie_on:
            raise ValueError("Target already has a pending skipped turn")
        state.players[target].has_pool_floatie_on = True
    elif upgrade_type in (UpgradeType.COFFEE, UpgradeType.MAG_GLASS) and state.rounds_remaining <= 0:
        raise ValueError("No rounds remain in the gun")

    setattr(player.upgrades, inventory_attribute, getattr(player.upgrades, inventory_attribute) - 1)
    if upgrade_type == UpgradeType.JUICE:
        player.health = min(state.max_health, player.health + 1)
    elif upgrade_type == UpgradeType.COFFEE:
        ejected_live = _consume_next_shell(state)
        for index, status in enumerate(state.player_ejection_view):
            if index == player_index:
                if ejected_live:
                    status.lives_ejected += 1
                else:
                    status.blanks_ejected += 1
            else:
                status.unknowns_ejected += 1
        if state.rounds_remaining == 0 and state.alive_players > 1:
            _start_upgrade_stage(state, player_index)
            return True
    elif upgrade_type == UpgradeType.MAG_GLASS:
        shell_index = len(state.round_contents) - state.rounds_remaining
        state.player_next_round_view = (
            NextRound.LIVE if state.round_contents[shell_index] else NextRound.BLANK
        )
    elif upgrade_type == UpgradeType.HAND_SAW:
        state.damage += 1
    return False

def initGame(seed: int, num_players: int = 2) -> GameState:
    if num_players < 2 or num_players > 4:
        raise ValueError("Buckshot roulette requires 2 to 4 players")

    state = GameState()
    state.rng = random.Random(seed)
    state.max_health = 5
    state.players = []
    for _ in range(num_players):
        player = Player()
        player.health = state.max_health
        player.upgrades = _new_upgrade_counts()
        player.has_pool_floatie_on = False
        state.players.append(player)
    state.alive_players = num_players
    state.stage = Stage.PLAY
    state.turn = 0
    state.session_no = 0
    state.game_over = False
    state.elimination_order = []
    _setup_round(state)
    return state


def eliminate_player(state: GameState, player_index: int) -> None:
    """Remove a player from the game outside of normal play (e.g. disqualification)."""
    player = state.players[player_index]
    if player.health <= 0 or state.game_over:
        return
    player.health = 0
    state.alive_players -= 1
    state.elimination_order.append(player_index)
    if state.alive_players <= 1:
        state.game_over = True
    elif state.turn == player_index:
        state.turn = _advance_turn(state, player_index, skip_floaties=False)
        state.player_next_round_view = NextRound.UNKNOWN


# public names for the engine
play_observation = _play_observation
upgrade_observation = _upgrade_observation


def step_PLAY(state: GameState, action: Action_PLAY) -> Obs_PLAY:
    if state.stage != Stage.PLAY or state.game_over:
        raise ValueError("The game is not accepting play actions")

    current_turn = state.turn
    if action.action == ActionType.USE_UPGRADE:
        upgrade_type = getattr(action, "useUpgrade", None)
        if upgrade_type is None:
            raise ValueError("An upgrade type is required")
        _use_upgrade(state, upgrade_type, getattr(action, "target", None))
        return _play_observation(state)

    if action.action != ActionType.SHOOT:
        raise ValueError("Unknown play action")
    target = getattr(action, "target", None)
    if target is None or target < 0 or target >= len(state.players):
        raise ValueError("Shooting requires a valid player target")
    if state.players[target].health <= 0:
        raise ValueError("Cannot shoot an eliminated player")
    if state.rounds_remaining <= 0:
        raise ValueError("No rounds remain in the gun")

    is_live = _consume_next_shell(state)
    if is_live:
        state.lives_shot += 1
        previous_health = state.players[target].health
        state.players[target].health = max(0, previous_health - state.damage)
        if previous_health > 0 and state.players[target].health == 0:
            state.alive_players -= 1
            state.elimination_order.append(target)
    else:
        state.blanks_shot += 1
    state.damage = 1

    if state.alive_players <= 1:
        state.game_over = True
    elif state.rounds_remaining == 0:
        _start_upgrade_stage(state, current_turn)
    elif not is_live and target == current_turn:
        return _play_observation(state)
    else:
        state.turn = _advance_turn(state, current_turn, skip_floaties=True)
    return _play_observation(state)


def step_PICK_UPGRADES(state: GameState, action: Action_PICK_UPGRADES) -> Obs_PICK_UPGRADES:
    if state.stage != Stage.PICK_UPGRADE or state.game_over:
        raise ValueError("The game is not accepting upgrade picks")
    if state.available_upgrades is None:
        raise ValueError("No upgrades are available")

    upgrade_type = action.chosen_upgrade
    count_attribute = {
        UpgradeType.JUICE: "juice",
        UpgradeType.COFFEE: "coffee",
        UpgradeType.MAG_GLASS: "mag_glass",
        UpgradeType.POOL_FLOATIE: "pool_floatie",
        UpgradeType.HAND_SAW: "hand_saw",
    }.get(upgrade_type)
    if count_attribute is None or getattr(state.available_upgrades, count_attribute) <= 0:
        raise ValueError("That upgrade is not available")

    player = state.players[state.turn]
    total_upgrades = sum(getattr(player.upgrades, name) for name in (
        "juice", "coffee", "mag_glass", "pool_floatie", "hand_saw"
    ))
    if total_upgrades < 15:
        setattr(player.upgrades, count_attribute, getattr(player.upgrades, count_attribute) + 1)
    setattr(state.available_upgrades, count_attribute, getattr(state.available_upgrades, count_attribute) - 1)

    current_turn = state.turn
    if sum(getattr(state.available_upgrades, name) for name in (
        "juice", "coffee", "mag_glass", "pool_floatie", "hand_saw"
    )) == 0:
        state.session_no += 1
        state.stage = Stage.PLAY
        state.turn = _advance_turn(state, current_turn, skip_floaties=True)
        _setup_round(state)
    else:
        state.turn = _advance_turn(state, current_turn, skip_floaties=True)
    return _upgrade_observation(state)

step_PICK_UPGRADE = step_PICK_UPGRADES
