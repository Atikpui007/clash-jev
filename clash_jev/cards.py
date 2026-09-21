"""Card facts: cost, kind, role and tags for every card id the hand reader or the troop network can produce.

`describe()` and `profile()` build what is sent for a card. Evolutions and heroes (`evo_x`, `hero_x`)
inherit their base card's entry.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Kind = Literal["troop", "building", "spell", "anywhere_troop"]

TAGS = {
    # movement and targeting
    "flying", "hits_air", "building_only",
    # damage shape and reach
    "single_target", "splash", "chain", "melee", "ranged", "long_range",
    # body and numbers
    "tank", "mini_tank", "fragile", "swarm", "pair",
    # speed (medium when neither is given)
    "slow", "fast", "very_fast",
    # job
    "win_condition", "defensive_building", "siege", "spawner", "cycle", "champion", "economy",
    # effects
    "stun", "slow_effect", "freeze", "knockback", "pull", "rage", "heal", "shield", "charge", "dash", "jump",
    "invisible", "death_damage", "death_spawn", "ramp_damage", "snare", "clone", "curse", "reflect",
    # spell size
    "light_damage", "medium_damage", "heavy_damage", "damages_buildings",
}  # fmt: skip


@dataclass(frozen=True)
class CardInfo:
    cost: int | None  # None: depends on context (mirror, spirit empress) or the card is unidentified
    kind: Kind
    role: str
    tags: frozenset[str] = frozenset()


def _c(cost: int | None, kind: Kind, role: str, tags: str = "") -> CardInfo:
    parsed = frozenset(tags.split())
    assert parsed <= TAGS, f"unknown tags: {parsed - TAGS}"
    return CardInfo(cost, kind, role, parsed)


UNKNOWN = CardInfo(cost=None, kind="troop", role="unidentified card")

_T, _B, _S, _A = "troop", "building", "spell", "anywhere_troop"

CARDS: dict[str, CardInfo] = {
    # --- win conditions -------------------------------------------------------------------------
    "giant": _c(5, _T, "slow tank that walks to buildings; needs support behind it", "building_only tank slow melee win_condition"),
    "royal_giant": _c(6, _T, "tank that shoots buildings from range", "building_only tank slow ranged win_condition"),
    "golem": _c(8, _T, "huge tank that splits into golemites; play from the back", "building_only tank slow melee win_condition death_spawn death_damage"),
    "electro_giant": _c(7, _T, "tank that zaps whatever attacks it", "building_only tank slow melee win_condition stun"),
    "goblin_giant": _c(6, _T, "tank carrying two spear goblins that shoot air and ground", "building_only tank melee win_condition hits_air death_spawn"),
    "rune_giant": _c(4, _T, "tank that enchants nearby allies for bonus damage", "building_only mini_tank melee"),
    "lava_hound": _c(7, _T, "flying tank that bursts into lava pups; play from the back", "flying building_only tank slow win_condition death_spawn"),
    "hog": _c(4, _T, "hog rider: fast attacker that jumps the river and hits buildings", "building_only very_fast melee win_condition jump"),
    "royal_hogs": _c(5, _T, "four fast hogs that split across lanes and hit buildings", "building_only very_fast melee win_condition swarm jump"),
    "ram_rider": _c(5, _T, "charging building attacker whose rider snares defenders", "building_only fast melee win_condition charge snare"),
    "battle_ram": _c(4, _T, "charging ram that hits buildings and releases two barbarians", "building_only fast melee win_condition charge death_spawn"),
    "balloon": _c(5, _T, "flying bomber that only hits buildings; deadly if it reaches a tower", "flying building_only melee win_condition death_damage"),
    "wall_breakers": _c(2, _T, "two cheap fast bombers that only hit buildings", "building_only very_fast pair fragile win_condition cycle splash"),
    "skeleton_barrel": _c(3, _T, "flying barrel that drops skeletons on buildings", "flying building_only win_condition death_spawn fragile"),
    "elixir_golem": _c(3, _T, "cheap tank that splits twice and gives the enemy elixir when it dies", "building_only tank melee death_spawn"),
    "miner": _c(3, _A, "mini tank deployable anywhere, usually on an enemy tower", "mini_tank melee win_condition single_target"),
    "goblin_drill": _c(4, _A, "building deployable anywhere that keeps spawning goblins", "win_condition spawner death_spawn"),
    "goblin_barrel": _c(3, _S, "drops three goblins on the target, usually an enemy tower", "win_condition swarm"),
    "graveyard": _c(5, _S, "spawns skeletons over an area for 9 seconds, usually on a tower", "win_condition swarm spawner"),
    "xbow": _c(6, _B, "siege building that shoots towers from your side of the bridge", "siege win_condition long_range single_target"),
    "mortar": _c(4, _B, "siege building that lobs splash shells at towers from your side", "siege win_condition long_range splash"),
    "three_musketeers": _c(9, _T, "three long-range shooters; huge value if they survive", "hits_air ranged single_target win_condition"),
    "suspicious_bush": _c(2, _T, "invisible bush that walks to buildings and releases two goblins", "building_only invisible death_spawn cycle"),
    # --- tanks and mini tanks -------------------------------------------------------------------
    "knight": _c(3, _T, "cheap sturdy melee fighter for defence and shielding support troops", "mini_tank melee single_target"),
    "valkyrie": _c(4, _T, "sturdy fighter whose spin hits everything around her; shreds ground swarms", "mini_tank melee splash"),
    "mini_pekka": _c(4, _T, "very high single hits; kills tanks and hog riders on defence", "melee single_target fast"),
    "pekka": _c(7, _T, "armoured heavy hitter; kills tanks, weak to swarms", "tank melee single_target slow"),
    "mega_knight": _c(7, _T, "tank that lands with splash and jumps onto targets; best dropped on a push", "tank melee splash jump"),
    "prince": _c(5, _T, "charges for double damage; strong if ignored, stopped by swarms", "mini_tank melee single_target charge fast"),
    "dark_prince": _c(4, _T, "shielded charger with splash", "mini_tank melee splash charge shield"),
    "ice_golem": _c(2, _T, "cheap walking distraction that slows on death", "building_only mini_tank melee slow cycle death_damage slow_effect"),
    "lumberjack": _c(4, _T, "very fast hard hitter that drops rage when he dies", "melee single_target very_fast death_spawn rage"),
    "bandit": _c(3, _T, "dashes to targets, invulnerable mid-dash", "melee single_target fast dash"),
    "royal_ghost": _c(3, _T, "invisible until he attacks; melee splash", "melee splash fast invisible"),
    "elite_barbarians": _c(6, _T, "two very fast heavy hitters; punishes low elixir", "melee single_target very_fast pair"),
    "barbarians": _c(5, _T, "five sturdy melee fighters; strong ground defence", "melee single_target swarm"),
    "giant_skeleton": _c(6, _T, "tank that drops a huge bomb when he dies", "tank melee single_target death_damage"),
    "royal_recruits": _c(7, _T, "six shielded recruits spread across both lanes", "melee single_target swarm shield"),
    "battle_healer": _c(4, _T, "sturdy fighter who heals allies around her as she attacks", "mini_tank melee single_target heal"),
    "fisherman": _c(3, _T, "hooks a distant enemy and pulls it to himself", "melee single_target pull slow_effect"),
    "berserker": _c(2, _T, "cheap very fast-hitting melee fighter", "melee single_target fast cycle"),
    "goblin_machine": _c(5, _T, "tank with a melee punch and a long-range rocket", "tank melee splash hits_air"),
    "cannon_cart": _c(5, _T, "shielded rolling cannon that becomes a building when the shield breaks", "ranged single_target shield"),
    # --- champions ------------------------------------------------------------------------------
    "archer_queen": _c(5, _T, "champion: fast-firing shooter whose ability turns her invisible", "champion hits_air ranged single_target invisible"),
    "golden_knight": _c(4, _T, "champion: fighter whose ability dashes through a chain of enemies", "champion melee single_target dash chain"),
    "skeleton_king": _c(4, _T, "champion: splash tank whose ability summons a skeleton army", "champion mini_tank melee splash spawner"),
    "mighty_miner": _c(4, _T, "champion: drill damage ramps up; ability swaps lanes and drops a bomb", "champion mini_tank melee single_target ramp_damage"),
    "monk": _c(5, _T, "champion: tank with knockback combo; ability reflects spells and projectiles", "champion mini_tank melee single_target knockback reflect"),
    "little_prince": _c(3, _T, "champion: shooter that speeds up while standing still; ability summons a guardian", "champion hits_air ranged single_target"),
    "goblinstein": _c(5, _T, "champion: ranged doctor plus a melee monster tank", "champion hits_air ranged stun tank"),
    "boss_bandit": _c(6, _T, "champion: heavy dashing fighter whose ability teleports her back", "champion mini_tank melee single_target dash"),
    "spirit_empress": _c(None, _T, "flying dragon rider for 6 elixir, or a ground spirit for 3; ranged, hits air", "hits_air ranged single_target"),
    # --- ranged support -------------------------------------------------------------------------
    "musketeer": _c(4, _T, "long-range shooter with solid damage", "hits_air ranged single_target"),
    "archers": _c(3, _T, "two cheap shooters", "hits_air ranged single_target pair"),
    "wizard": _c(5, _T, "splash fireballs; destroys swarms", "hits_air ranged splash"),
    "baby_dragon": _c(4, _T, "flying sturdy splash attacker", "flying hits_air ranged splash mini_tank"),
    "electro_wizard": _c(4, _T, "stuns two targets per shot and zaps on landing; resets charges and infernos", "hits_air ranged stun"),
    "ice_wizard": _c(3, _T, "slows everything he hits; low damage, great on defence", "hits_air ranged splash slow_effect"),
    "witch": _c(5, _T, "splash shooter who keeps summoning skeletons", "hits_air ranged splash spawner"),
    "night_witch": _c(4, _T, "melee fighter who keeps summoning bats", "melee single_target spawner death_spawn"),
    "mother_witch": _c(4, _T, "curses targets so they turn into hogs when they die", "hits_air ranged single_target curse"),
    "executioner": _c(5, _T, "axe pierces through everything in a line and returns", "hits_air ranged splash"),
    "hunter": _c(4, _T, "shotgun blast: enormous damage up close, little at range", "hits_air ranged splash"),
    "magic_archer": _c(4, _T, "arrow pierces through everything in a long line", "hits_air long_range splash"),
    "princess": _c(3, _T, "splash arrows from beyond tower range", "hits_air long_range splash fragile"),
    "dart_goblin": _c(3, _T, "very fast, long-range blowpipe", "hits_air long_range single_target very_fast fragile"),
    "fire_cracker": _c(3, _T, "firework splits into a spread; she recoils backwards each shot", "hits_air long_range splash fragile"),
    "bomber": _c(2, _T, "cheap ground splash bomber", "ranged splash fragile cycle"),
    "bowler": _c(5, _T, "rolls a boulder through ground troops in a line with knockback", "mini_tank ranged splash knockback slow"),
    "mega_minion": _c(3, _T, "flying armoured single-target hitter", "flying hits_air melee single_target"),
    "inferno_dragon": _c(4, _T, "flying beam whose damage ramps up; melts tanks, reset by stuns", "flying hits_air ranged single_target ramp_damage"),
    "electro_dragon": _c(5, _T, "flying chain lightning that stuns three targets", "flying hits_air ranged chain stun"),
    "flying_machine": _c(4, _T, "flying long-range shooter", "flying hits_air long_range single_target fragile"),
    "skeleton_dragons": _c(4, _T, "two flying splash dragons", "flying hits_air ranged splash pair"),
    "phoenix": _c(4, _T, "flying fighter that turns into an egg and revives once", "flying hits_air melee single_target death_spawn death_damage"),
    "sparky": _c(6, _T, "slow-charging cannon with massive splash; reset by stuns", "ranged splash slow mini_tank"),
    "zappies": _c(4, _T, "three shooters that stun", "hits_air ranged single_target stun"),
    "rascals": _c(5, _T, "one sturdy boy in front and two girls with slingshots behind", "hits_air mini_tank ranged single_target"),
    "furnace": _c(4, _T, "walking furnace that shoots from range and keeps releasing fire spirits", "ranged spawner hits_air"),
    "goblin_demolisher": _c(4, _T, "throws splash bombs, then charges buildings to explode when hurt", "ranged splash death_damage"),
    # --- swarms and cycle -----------------------------------------------------------------------
    "skeletons": _c(1, _T, "three skeletons; cheapest distraction", "melee single_target swarm fragile fast cycle"),
    "ice_spirit": _c(1, _T, "jumps onto a target and freezes an area briefly", "hits_air splash freeze fragile very_fast cycle"),
    "fire_spirit": _c(1, _T, "jumps onto a target for splash damage", "hits_air splash fragile very_fast cycle"),
    "electro_spirit": _c(1, _T, "jumps onto a target and chains a stun across nine enemies", "hits_air chain stun fragile very_fast cycle"),
    "heal_spirit": _c(1, _T, "jumps onto a target and heals allies around it", "hits_air splash heal fragile very_fast cycle"),
    "goblins": _c(2, _T, "cheap fast stabbers", "melee single_target swarm fragile very_fast cycle"),
    "spear_goblins": _c(2, _T, "cheap spear throwers", "hits_air ranged single_target swarm fragile very_fast cycle"),
    "goblin_gang": _c(3, _T, "three stab goblins and three spear goblins", "hits_air melee ranged swarm fragile very_fast"),
    "bats": _c(2, _T, "cheap flying swarm", "flying hits_air melee single_target swarm fragile very_fast cycle"),
    "minions": _c(3, _T, "three flying attackers", "flying hits_air melee single_target swarm fragile fast"),
    "minion_horde": _c(5, _T, "six flying attackers; dies to arrows", "flying hits_air melee single_target swarm fragile fast"),
    "skeleton_army": _c(3, _T, "fifteen skeletons; shreds single-target troops, dies to any splash", "melee single_target swarm fragile fast"),
    "guards": _c(3, _T, "three shielded skeletons", "melee single_target swarm shield fast"),
    # --- buildings ------------------------------------------------------------------------------
    "cannon": _c(3, _B, "cheap ground-only defence; pulls building attackers to the centre", "defensive_building ranged single_target"),
    "tesla": _c(4, _B, "hides underground; zaps air and ground", "defensive_building hits_air ranged single_target stun"),
    "inferno_tower": _c(5, _B, "beam whose damage ramps up; melts tanks, reset by stuns", "defensive_building hits_air ranged single_target ramp_damage"),
    "bomb_tower": _c(4, _B, "ground splash defence that drops a bomb when destroyed", "defensive_building ranged splash death_damage"),
    "goblin_cage": _c(4, _B, "cage that releases a goblin brawler when destroyed", "defensive_building death_spawn"),
    "tombstone": _c(3, _B, "spawns skeletons over time and on death; distracts attackers", "defensive_building spawner death_spawn"),
    "goblin_hut": _c(5, _B, "spawns spear goblins", "spawner hits_air"),
    "barb_hut": _c(6, _B, "spawns barbarians", "spawner"),
    "elixir_collector": _c(6, _B, "produces elixir over time; play only when no attack is coming", "economy"),
    # --- spells ---------------------------------------------------------------------------------
    "fireball": _c(4, _S, "medium radius; kills support troops and chips towers", "medium_damage damages_buildings knockback"),
    "arrows": _c(3, _S, "wide radius; clears swarms", "light_damage"),
    "zap": _c(2, _S, "instant small radius with a stun; resets charges and infernos", "light_damage stun cycle"),
    "log": _c(2, _S, "rolls along the ground with knockback; ground troops only", "light_damage knockback cycle"),
    "snowball": _c(2, _S, "small radius with knockback and slow", "light_damage knockback slow_effect cycle"),
    "barb_barrel": _c(2, _S, "short ground roll that leaves a barbarian", "light_damage cycle"),
    "royal_delivery": _c(3, _S, "drops on your own side only: area damage, then a royal recruit", "medium_damage"),
    "poison": _c(4, _S, "damage over 8 seconds across a wide area; denies an area", "medium_damage damages_buildings slow_effect"),
    "rocket": _c(6, _S, "huge damage in a small radius; finishes towers", "heavy_damage damages_buildings"),
    "lightning": _c(6, _S, "strikes the three strongest targets in the area and stuns them", "heavy_damage damages_buildings stun"),
    "earthquake": _c(3, _S, "ground-only damage over time, heavy against buildings", "light_damage damages_buildings slow_effect"),
    "freeze": _c(4, _S, "freezes troops and buildings in the area for 4 seconds", "freeze"),
    "rage": _c(2, _S, "speeds up your troops in the area", "rage cycle"),
    "tornado": _c(3, _S, "drags troops to its centre; pulls attackers to your king tower", "pull light_damage"),
    "clone": _c(3, _S, "copies your troops in the area as one-hit clones", "clone"),
    "gob_curse": _c(2, _S, "goblin curse: enemies in the area take more damage and turn into goblins on death", "curse light_damage cycle"),
    "vines": _c(3, _S, "roots the three strongest targets in the area and pulls flyers down", "snare light_damage"),
    "void": _c(3, _S, "three pulses; hits hardest when few targets are inside", "medium_damage damages_buildings"),
    "mirror": _c(None, _S, "replays the card you played last, one level higher, for one more elixir", ""),
}  # fmt: skip

# Levels that the tags alone would get wrong. Everything else is derived in profile().
_HEALTH = {
    "very high": {"golem", "giant", "royal_giant", "electro_giant", "goblin_giant", "lava_hound", "pekka", "mega_knight", "giant_skeleton", "elixir_golem"},
    "high": {"knight", "valkyrie", "ice_golem", "prince", "dark_prince", "bowler", "baby_dragon", "balloon", "battle_healer", "rune_giant", "skeleton_king", "monk", "mighty_miner", "boss_bandit", "goblin_machine", "miner", "ram_rider", "hog", "royal_hogs", "battle_ram", "barbarians", "elite_barbarians", "royal_recruits", "cannon_cart", "sparky", "rascals", "goblinstein", "golden_knight", "inferno_tower", "bomb_tower", "xbow", "elixir_collector", "barb_hut", "goblin_hut"},
    "low": {"musketeer", "wizard", "electro_wizard", "ice_wizard", "witch", "night_witch", "mother_witch", "executioner", "hunter", "magic_archer", "archers", "bomber", "zappies", "three_musketeers", "archer_queen", "little_prince", "spirit_empress", "guards", "bandit", "royal_ghost", "berserker", "fisherman", "mega_minion", "inferno_dragon", "electro_dragon", "skeleton_dragons", "phoenix", "goblin_demolisher", "furnace", "cannon", "tesla", "mortar", "tombstone", "goblin_cage", "goblin_drill", "suspicious_bush"},
}  # fmt: skip
_DAMAGE = {
    "very high": {"pekka", "mini_pekka", "sparky", "balloon", "prince", "elite_barbarians", "inferno_tower", "inferno_dragon", "rocket", "lightning", "hunter"},
    "high": {"lumberjack", "musketeer", "three_musketeers", "mega_knight", "giant_skeleton", "royal_giant", "xbow", "wizard", "executioner", "magic_archer", "archer_queen", "bandit", "boss_bandit", "mighty_miner", "golden_knight", "monk", "valkyrie", "bowler", "dark_prince", "ram_rider", "hog", "royal_hogs", "battle_ram", "wall_breakers", "fireball", "poison", "goblin_machine", "electro_dragon", "skeleton_dragons", "phoenix", "barbarians", "berserker", "night_witch", "cannon_cart", "goblin_demolisher", "firecracker", "fire_cracker", "mortar", "tesla"},
    "low": {"ice_wizard", "ice_golem", "ice_spirit", "electro_spirit", "heal_spirit", "fire_spirit", "skeletons", "bats", "zap", "log", "snowball", "arrows", "barb_barrel", "earthquake", "tornado", "gob_curse", "vines", "giant", "golem", "lava_hound", "electro_giant", "elixir_golem", "battle_healer", "fisherman", "tombstone", "royal_delivery"},
    "none": {"elixir_collector", "rage", "clone", "freeze", "mirror"},
}  # fmt: skip
# How much ground a spell covers.
_SPELL_AREA = {
    "arrows": "large circle", "poison": "large circle", "graveyard": "large circle", "earthquake": "medium circle",
    "fireball": "medium circle", "freeze": "medium circle", "rage": "medium circle", "tornado": "medium circle",
    "clone": "medium circle", "gob_curse": "medium circle", "lightning": "the three strongest targets in a medium circle",
    "vines": "the three strongest targets in a medium circle", "zap": "small circle", "snowball": "small circle",
    "rocket": "small circle", "void": "small circle", "royal_delivery": "small circle",
    "goblin_barrel": "a single point", "log": "a line rolling forward along the ground",
    "barb_barrel": "a short line rolling forward along the ground",
}  # fmt: skip
_EFFECT_TAGS = (
    "splash", "chain", "stun", "slow_effect", "freeze", "knockback", "pull", "rage", "heal", "shield", "charge",
    "dash", "jump", "invisible", "death_damage", "death_spawn", "ramp_damage", "snare", "clone", "curse", "reflect",
    "spawner", "damages_buildings",
)  # fmt: skip


def _level(table: dict[str, set[str]], base: str, default: str) -> str:
    return next((level for level, names in table.items() if base in names), default)


# Name, rarity and unlock arena of each card, from RoyaleAPI's public card data.
_OFFICIAL = json.loads(Path(__file__).with_name("official_cards.json").read_text())


def official(name: str) -> dict:
    return _OFFICIAL.get(base_name(name), {})


def unlock_arena(name: str) -> int | None:
    """The arena this card unlocks in (0 = training camp). None when the card data does not say."""
    return official(name).get("arena")


def unlocked_by(arena: int) -> set[str]:
    """Every base card a player in this arena can own. Cards the data has no arena for are left out."""
    return {name for name in CARDS if unlock_arena(name) is not None and unlock_arena(name) <= arena}


# Archetypes: the labels players use for what a card is. A card can carry several. What each one
# means is defined in game.py ARCHETYPES.
_TANK_BUSTERS = {
    "mini_pekka", "pekka", "prince", "elite_barbarians", "inferno_tower", "inferno_dragon", "hunter", "sparky",
    "lumberjack", "mighty_miner",
}  # fmt: skip
_UTILITY_SPELLS = {"freeze", "rage", "clone", "tornado", "mirror", "gob_curse", "vines"}


def archetypes(name: str) -> list[str]:
    if not known(name):
        return []
    card, base = info(name), base_name(name)
    tags = card.tags
    if card.kind == "spell":
        if base in _UTILITY_SPELLS:
            return ["utility spell"]
        size = (
            "big spell"
            if "heavy_damage" in tags
            else "medium spell"
            if "medium_damage" in tags
            else "small spell"
        )
        return [size, *(["win condition"] if "win_condition" in tags else [])]
    found = []
    if "win_condition" in tags:
        found.append("win condition")
    if "tank" in tags:
        found.append("tank")
    if "mini_tank" in tags:
        found.append("mini tank")
    if base in _TANK_BUSTERS:
        found.append("tank buster")
    if _level(_DAMAGE, base, "medium") in ("high", "very high") and "building_only" not in tags:
        found.append("high damage")
    if "splash" in tags or "chain" in tags:
        found.append("splash")
    if "swarm" in tags:
        found.append("swarm")
    if {"ranged", "long_range"} & tags and not {"tank", "mini_tank"} & tags and card.kind != "building":
        found.append("ranged support")
    if "hits_air" in tags:
        found.append("anti-air")
    if "flying" in tags:
        found.append("air troop")
    if "building_only" in tags:
        found.append("building targeter")
    if card.kind == "building" or base == "goblin_drill":
        found.append(
            "siege building"
            if "siege" in tags
            else "defensive building"
            if "defensive_building" in tags
            else "building"
        )
    if "spawner" in tags:
        found.append("spawner")
    if card.cost is not None and card.cost <= 2:
        found.append("cycle card")
    return found or ["melee fighter"]


# What a card is, in plain words: what it does, what it is strong against and what it is weak against.
# Covers the cards of the training camp and arena 1.
_DESCRIBED: dict[str, tuple[str, list[str], list[str]]] = {
    "giant": (
        (
            "One big, slow ground troop. Attacks only buildings and towers and never fights troops. Tanky: very high "
            "health, absorbs a lot of damage. Low damage per hit."
        ),
        [
            "Absorbs a lot of damage, so whatever is near it survives longer",
            "Walks past enemy troops, straight to the nearest building or tower",
            "Survives spells",
        ],
        [
            "Cannot attack troops at all, so it never kills what is hitting it",
            "Slow",
            "High-damage single-target troops (tank busters) and swarms take it down while it cannot hit back",
        ],
    ),
    "knight": (
        (
            "One ground melee troop. Sturdy: high health. Medium damage, one target at a time. "
            "Only attacks ground troops and buildings: it cannot attack anything that flies."
        ),
        ["High health: takes many hits before dying", "Survives spells"],
        [
            "Cannot attack flying troops",
            "Hits one target at a time, so a swarm surrounds it",
            "Tank busters kill it quickly",
        ],
    ),
    "mini_pekka": (
        (
            "One fast ground melee troop. Very high damage per hit, one target at a time. Medium health. Only "
            "attacks ground troops and buildings: it cannot attack anything that flies."
        ),
        [
            "Kills high-health troops (tanks and mini tanks) in a few hits",
            "Deals heavy damage to a tower if it reaches one",
        ],
        [
            "Cannot attack flying troops",
            "Hits one target at a time, so a swarm soaks up its hits and surrounds it",
            "Short reach: ranged troops hit it before it arrives",
        ],
    ),
    "musketeer": (
        (
            "One ranged ground troop with a long reach. High damage, one target at a time. Low health. Attacks "
            "flying and ground troops and buildings."
        ),
        [
            "Can attack flying troops",
            "Hits from a distance, out of reach of melee troops",
            "High damage for a ranged troop",
        ],
        [
            "Low health: dies quickly once something reaches her",
            "A medium spell such as fireball kills or nearly kills her",
            "Hits one target at a time, so a swarm overwhelms her",
        ],
    ),
    "archers": (
        (
            "Two ranged ground troops. Medium damage each, one target at a time. Low health each. Attack flying and "
            "ground troops and buildings."
        ),
        [
            "Can attack flying troops",
            "Hit from a distance, out of reach of melee troops",
            "Two separate units: a single-target attacker has to kill them one by one",
        ],
        ["Low health: die quickly once something reaches them", "Splash damage and spells hit both at once"],
    ),
    "minions": (
        (
            "Three fast flying melee troops. Medium damage each. Very low health each. Attack flying and ground "
            "troops and buildings."
        ),
        [
            "They fly: troops that attack ground only cannot touch them",
            "Can attack flying troops",
            "Three units dealing damage at once: high combined damage",
        ],
        [
            "Very low health: a small spell such as arrows kills all three",
            "Splash damage that reaches air hits all of them at once",
        ],
    ),
    "spear_goblins": (
        (
            "Three very fast ranged ground troops. Low damage each. Very low health each. Attack flying and ground "
            "troops and buildings."
        ),
        ["Can attack flying troops", "Hit from a distance"],
        ["Very low health: any spell or splash damage kills all three", "Low damage"],
    ),
    "goblins": (
        (
            "A group of very fast ground melee troops. Medium damage each, high combined. Very low health each. Only "
            "attack ground troops and buildings: they cannot attack anything that flies."
        ),
        [
            "High combined damage",
            "Several units: they surround a single-target attacker",
            "Very fast",
        ],
        ["Cannot attack flying troops", "Very low health: any spell or splash damage kills them all"],
    ),
    "goblin_hut": (
        (
            "A building. It does not attack: while it stands it keeps producing spear goblins, one after another, "
            "which walk down the lane it is in. Like every building it loses health over time until it disappears."
        ),
        [
            "One card produces many troops over time",
            "As a building it draws troops that attack only buildings (such as a giant) toward itself",
        ],
        [
            "The spear goblins it produces have very low health and die to any spell or splash damage",
            "The troops arrive slowly, one at a time",
            "Spells damage it",
        ],
    ),
    "goblin_cage": (
        (
            "A building. It does not attack. When it is destroyed or its time runs out, it releases a goblin "
            "brawler: one ground melee troop with medium health and high damage."
        ),
        [
            "As a building it draws troops that attack only buildings (such as a giant) toward itself",
            "Whatever destroys the cage then has to deal with the brawler as well",
        ],
        [
            "Neither the cage nor the brawler can attack flying troops",
            "Does nothing until it is attacked or its time runs out",
        ],
    ),
    "bomber": (
        (
            "One ranged ground troop that throws bombs. Each bomb hits everything on the ground in a small area "
            "(splash). Very low health. Only attacks ground troops and buildings: it cannot attack anything that flies."
        ),
        [
            "One bomb hits a whole group of ground troops at once: strong against swarms such as goblins and skeletons",
            "Hits from a distance",
        ],
        [
            "Cannot attack flying troops",
            "Very low health: dies quickly once something reaches it, and to any spell",
        ],
    ),
    "skeletons": (
        (
            "A small group of fast ground melee troops. Low damage each. Almost no health: one hit kills one. "
            "Only attack ground troops and buildings: they cannot attack anything that flies."
        ),
        [
            "Several units: they surround a single-target attacker, which has to kill them one at a time",
            "Fast",
        ],
        [
            "Cannot attack flying troops",
            "Any spell or splash damage kills them all at once",
        ],
    ),
    "valkyrie": (
        (
            "One ground melee troop. Sturdy: high health. Her spin hits everything on the ground around her (splash). "
            "Only attacks ground troops and buildings: she cannot attack anything that flies."
        ),
        [
            "Hits every ground troop around her at once: strong against swarms",
            "High health: takes many hits before dying",
            "Survives spells",
        ],
        [
            "Cannot attack flying troops",
            "Short reach: ranged troops hit her before she arrives",
            "Tank busters kill her quickly",
        ],
    ),
    "tombstone": (
        (
            "A building. It does not attack: while it stands it keeps producing skeletons, and when it is destroyed or "
            "its time runs out it releases several more. Like every building it loses health over time."
        ),
        [
            "As a building it draws troops that attack only buildings (such as a giant) toward itself",
            "The skeletons it produces surround single-target attackers",
        ],
        [
            "The skeletons die to any spell or splash damage",
            "Spells damage it",
        ],
    ),
    "fireball": (
        (
            "A spell. Instant medium damage to everything in a medium circle, in the air or on the ground, with a "
            "small knockback. Damages towers too, for much less."
        ),
        [
            "Kills a whole swarm caught in its circle: goblins, spear goblins, skeletons and minions all die to it",
            "Kills or nearly kills low-health troops such as musketeer, archers and bomber",
            "Hits every troop in the circle at once, in the air or on the ground",
            "Reaches anywhere on the arena, including an enemy tower",
        ],
        [
            "Does little to high-health troops such as a giant or a knight",
            "Leaves nothing on the arena afterwards",
            "Troops that are spread out are not all inside the circle",
        ],
    ),
    "arrows": (
        (
            "A spell. Instant light damage to everything in a large circle, in the air or on the ground. Damages "
            "towers too, for very little."
        ),
        [
            "Kills a whole swarm at once: minions, goblins, spear goblins and skeletons all die to it",
            "The large circle catches troops that are spread out",
            "Reaches anywhere on the arena",
        ],
        [
            "Does little to anything with low health or more",
            "Leaves nothing on the arena afterwards",
        ],
    ),
}


def describe(name: str) -> dict:
    """{description, strengths, weaknesses} for the cards that have a description. Empty for the others."""
    described = _DESCRIBED.get(base_name(name))
    if described is None:
        return {}
    description, strengths, weaknesses = described
    return {"description": description, "strengths": strengths, "weaknesses": weaknesses}


def card_class(name: str) -> str:
    card, base = info(name), base_name(name)
    if not known(name):
        return "unknown"
    if card.kind == "spell":
        return "spell"
    if card.kind == "building" or base == "goblin_drill":
        return (
            "siege building"
            if "siege" in card.tags
            else "defensive building"
            if "defensive_building" in card.tags
            else "building"
        )
    labels = (
        ("win_condition", "win condition"),
        ("tank", "tank"),
        ("mini_tank", "mini tank"),
        ("swarm", "swarm"),
    )
    for tag, label in labels:
        if tag in card.tags:
            return label
    return "ranged support" if {"ranged", "long_range"} & card.tags else "melee fighter"


def profile(name: str) -> dict:
    """The structured description sent for a card in hand or an identified troop."""
    if not known(name):
        return {"class": "unknown", "archetypes": []}
    card, base = info(name), base_name(name)
    if card.kind == "spell":
        targets = "ground only" if base in _GROUND_ONLY_SPELLS else "air and ground"
        health = None
    else:
        targets = (
            "buildings only"
            if "building_only" in card.tags
            else "air and ground"
            if "hits_air" in card.tags
            else "ground only"
        )
        fallback = "very low" if "fragile" in card.tags or "swarm" in card.tags else "medium"
        health = _level(_HEALTH, base, fallback)
    speed = next(
        (tag.replace("_", " ") for tag in ("very_fast", "fast", "slow") if tag in card.tags), "medium"
    )
    return {
        "type": "troop"
        if card.kind == "anywhere_troop"
        else card.kind,  # troop, building or spell: game.card_types
        "class": card_class(name),
        "archetypes": archetypes(name),
        "health": health,
        "damage": _level(_DAMAGE, base, "medium"),
        "targets": targets,
        "flies": "flying" in card.tags,
        "speed": None if card.kind in ("spell", "building") else speed,
        "count": "many" if "swarm" in card.tags else "two" if "pair" in card.tags else "one",
        "area": _SPELL_AREA.get(base) if card.kind == "spell" else None,
        "abilities": [tag.replace("_", " ") for tag in _EFFECT_TAGS if tag in card.tags],
        "rarity": official(name).get("rarity"),
        **describe(name),
    }


_GROUND_ONLY_SPELLS = {"log", "barb_barrel", "earthquake"}


def base_name(name: str) -> str:
    """Evolutions and heroes play like their base card."""
    for prefix in ("evo_", "hero_"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def known(name: str | None) -> bool:
    return bool(name) and base_name(name) in CARDS


def info(name: str) -> CardInfo:
    return CARDS.get(base_name(name), UNKNOWN)


def tags(name: str) -> list[str]:
    variant = {"evo_": "evolution", "hero_": "hero"}
    return sorted(info(name).tags) + [label for prefix, label in variant.items() if name.startswith(prefix)]


def hits_air(name: str) -> bool | None:
    """None when the card is not in the table, so nothing false is claimed about it."""
    if not known(name):
        return None
    return info(name).kind == "spell" or "hits_air" in info(name).tags
