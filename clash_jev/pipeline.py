"""The whole bot, one step at a time:

state   = extract_state(screenshot)
options = get_valid_moves(state)
move    = choose_with_jev(state, options)
click_card(move.card.slot); click_square(move.square)
"""

from clash_jev.device import AdbDevice
from clash_jev.hand import HAND_TAP_POINTS
from clash_jev.moves import CardMoves, Square, get_valid_moves
from clash_jev.perception import Perception
from clash_jev.policy import Decision, JevPolicy
from clash_jev.screenmap import ScreenMap
from clash_jev.state import BattleState

__all__ = ["choose_with_jev", "click_card", "click_square", "extract_state", "get_valid_moves", "step"]

_perception = Perception()
_jev: JevPolicy | None = None


def extract_state(screenshot, elapsed_s: float = 0.0) -> BattleState:
    return _perception.extract_state(screenshot, elapsed_s)


def choose_with_jev(state: BattleState, options: list[CardMoves]) -> Decision:
    global _jev
    if _jev is None:
        _jev = JevPolicy()
    return _jev.decide(state, options)


def _tap_fraction(device: AdbDevice, screenshot, xy: tuple[float, float]) -> None:
    # Taps land in the device's real pixels; frames may arrive smaller (video stream).
    size = device.screen_size() if hasattr(device, "screen_size") else screenshot.shape[1::-1]
    device.tap(*ScreenMap(*size).to_device(xy))


def play_card(device: AdbDevice, screenshot, card_slot: int, square: Square) -> None:
    """click_card + click_square as one fast action when the device supports it."""
    size = device.screen_size() if hasattr(device, "screen_size") else screenshot.shape[1::-1]
    screen = ScreenMap(*size)
    if hasattr(device, "play"):
        device.play(screen.to_device(HAND_TAP_POINTS[card_slot]), screen.to_device(square.xy))
    else:
        click_card(device, screenshot, card_slot)
        click_square(device, screenshot, square)


def click_card(device: AdbDevice, screenshot, card_slot: int) -> None:
    _tap_fraction(device, screenshot, HAND_TAP_POINTS[card_slot])


def click_square(device: AdbDevice, screenshot, square: Square) -> None:
    _tap_fraction(device, screenshot, square.xy)


def step(device: AdbDevice) -> Decision | None:
    """Capture -> decide -> act, once. None when no battle is on screen or nothing is playable."""
    screenshot = device.frame()
    state = extract_state(screenshot)
    options = get_valid_moves(state)
    if not options:
        return None
    move = choose_with_jev(state, options)
    if move.card is not None and move.square is not None:
        play_card(device, screenshot, move.card.slot, move.square)
    return move
