"""Train the troop network on your own named pictures:  clash-jev train --collect DIR

Needs PyTorch (`pip install -e ".[train]"`). Reads DIR/labels.json (written by `clash-jev label`), tests the
network on held-out play, then trains it on everything and writes clash_jev/troop_model.onnx and .json.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy

from clash_jev.label import NOT_A_TROOP, UNCLEAR, shows_its_badge
from clash_jev.troops import MODEL, MODEL_FACTS, SIZE, network_input

_MIN_PICTURES = (
    15  # a card with fewer usable pictures than this is left out: the network would only guess at it
)
_EPOCHS = 40
_FOLDS = 5


def load_pictures(folder: Path) -> list[dict]:
    """Every usable named picture: {input, card, track, minute}."""
    pictures = []
    for track, entry in enumerate(json.loads((folder / "labels.json").read_text())):
        if entry["label"] in (UNCLEAR, NOT_A_TROOP):
            continue
        for name in entry["pictures"]:
            path = folder / name
            if shows_its_badge(path):
                minute = int(path.stem.split("_")[0]) // 60_000
                pictures.append({"input": network_input(cv2.imread(str(path))), "card": entry["label"], "track": track, "minute": minute})  # fmt: skip
    counts = Counter(picture["card"] for picture in pictures)
    return [picture for picture in pictures if counts[picture["card"]] >= _MIN_PICTURES]


def _network(cards: int):
    from torch import nn

    def block(inputs: int, outputs: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Conv2d(inputs, outputs, 3, padding=1), nn.BatchNorm2d(outputs), nn.ReLU(),
            nn.Conv2d(outputs, outputs, 3, padding=1), nn.BatchNorm2d(outputs), nn.ReLU(), nn.MaxPool2d(2),
        )  # fmt: skip

    return nn.Sequential(
        block(3, 24), block(24, 48), block(48, 96), block(96, 128),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(128, cards),
    )  # fmt: skip


def _varied(inputs: numpy.ndarray, rng: numpy.random.Generator) -> numpy.ndarray:
    """Augment the pictures: mirrored, shifted, lighter or darker, and with red and blue swapped, so that
    one side's pictures teach the network both team colours."""
    varied = []
    for picture in inputs:
        if rng.random() < 0.5:
            picture = picture[:, :, ::-1]
        if rng.random() < 0.5:
            picture = picture[::-1]
        shift_x, shift_y = rng.integers(-SIZE // 14, SIZE // 14 + 1, 2)
        picture = numpy.roll(numpy.roll(picture, shift_x, 2), shift_y, 1)
        varied.append(picture * rng.uniform(0.8, 1.2) + rng.uniform(-0.2, 0.2))
    return numpy.ascontiguousarray(numpy.stack(varied), dtype=numpy.float32)


def _fit(inputs: numpy.ndarray, answers: numpy.ndarray, cards: int, seed: int = 0):
    import torch

    torch.manual_seed(seed)
    rng = numpy.random.default_rng(seed)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    network = _network(cards).to(device)
    # Rare cards count as much as common ones.
    weight = torch.tensor(
        [1.0 / max(1, (answers == card).sum()) for card in range(cards)], dtype=torch.float32
    )
    loss = torch.nn.CrossEntropyLoss(weight=(weight / weight.sum() * cards).to(device), label_smoothing=0.1)
    steps = _EPOCHS * ((len(inputs) + 31) // 32)
    optimiser = torch.optim.AdamW(network.parameters(), 2e-3, weight_decay=1e-2)
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=2e-3, total_steps=steps)
    for _ in range(_EPOCHS):
        network.train()
        order = rng.permutation(len(inputs))
        for start in range(0, len(order), 32):
            batch = order[start : start + 32]
            if len(batch) < 2:
                continue
            optimiser.zero_grad()
            scores = network(torch.from_numpy(_varied(inputs[batch], rng)).to(device))
            loss(scores, torch.from_numpy(answers[batch]).to(device)).backward()
            optimiser.step()
            schedule.step()
    return network.eval().cpu()


def _scores(network, inputs: numpy.ndarray) -> numpy.ndarray:
    import torch

    with torch.no_grad():
        return torch.softmax(network(torch.from_numpy(inputs)), 1).numpy()


def train(folder: Path, test: bool = True) -> dict:
    import torch

    pictures = load_pictures(folder.resolve())
    cards = sorted({picture["card"] for picture in pictures})
    inputs = numpy.stack([picture["input"] for picture in pictures]).astype(numpy.float32)
    answers = numpy.array([cards.index(picture["card"]) for picture in pictures])
    print(
        f"{len(pictures)} usable pictures of {len(cards)} cards: {dict(Counter(p['card'] for p in pictures))}"
    )

    report: dict = {"cards": cards, "pictures": len(pictures)}
    if test:
        # Tested on whole minutes of play the network never saw, so the same troop is never on both sides.
        minutes = sorted({picture["minute"] for picture in pictures})
        fold = numpy.array([minutes.index(picture["minute"]) % _FOLDS for picture in pictures])
        scores = numpy.zeros((len(pictures), len(cards)))
        for held_out in range(_FOLDS):
            test_on = fold == held_out
            scores[test_on] = _scores(_fit(inputs[~test_on], answers[~test_on], len(cards)), inputs[test_on])
        by_track: dict[int, list[int]] = defaultdict(list)
        for index, picture in enumerate(pictures):
            by_track[picture["track"]].append(index)
        right: Counter[str] = Counter()
        total: Counter[str] = Counter()
        for indices in by_track.values():
            card = cards[answers[indices[0]]]
            total[card] += 1
            right[card] += int(scores[indices].mean(0).argmax() == answers[indices[0]])
        report["troops_named_right"] = round(sum(right.values()) / sum(total.values()), 3)
        report["per_card"] = {card: f"{right[card]}/{total[card]}" for card in cards}
        print(
            f"On play it had not seen it names {report['troops_named_right']:.0%} of troops right: {report['per_card']}"
        )

    network = _fit(inputs, answers, len(cards))
    torch.onnx.export(
        network, torch.from_numpy(inputs[:4]), str(MODEL), input_names=["pictures"], output_names=["scores"],
        dynamic_axes={"pictures": {0: "n"}, "scores": {0: "n"}}, opset_version=13, dynamo=False,
    )  # fmt: skip
    MODEL_FACTS.write_text(json.dumps(report, indent=1))
    print(f"Wrote {MODEL} ({MODEL.stat().st_size / 1e6:.1f} MB) and {MODEL_FACTS.name}")
    return report
