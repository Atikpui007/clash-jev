"""The briefing sent with every request: what game this is, what winning means, how the arena and
elixir work, and what the terms used in the state and the questions mean. Rules and vocabulary only.
"""

GAME = {
    "name": "Clash Royale",
    "what_it_is": (
        "A real-time, one-against-one card battle. Both players deploy cards onto a shared arena at the "
        "same time; deployed troops move and fight on their own. You are one of the two players, acting "
        "through this interface: each request describes the match at this instant and asks for your next choice."
    ),
    "how_you_play": (
        "You see the match as a series of snapshots, one every `clock.seconds_between_snapshots` seconds. Each "
        "snapshot is one decision: you choose a strategy, and if it involves playing, a card and where it goes. "
        "Whatever you choose applies now, and you are asked again at the next snapshot, so anything you do not "
        "do now can still be done then. One exception: when you choose to play nothing (save_elixir or "
        "hold_elixir_for_threat), you are next asked once your elixir has gone up by one, or at once if a new "
        "enemy troop appears or one of your towers takes damage."
    ),
    "objective": (
        "Your goal is to destroy the enemy's towers — above all their king tower — before they destroy yours. "
        "Destroy more of the opponent's towers than they destroy of yours before time runs out. Each side has "
        "three towers: two princess towers and one king tower. Destroying the enemy king tower wins the match "
        "immediately. A match lasts 3 minutes; if towers destroyed are equal it goes to overtime, where the next "
        "tower destroyed wins, and if overtime also ends level the side whose weakest tower has more health wins."
    ),
    "arena": (
        "The arena is split by a river into your side (bottom) and the opponent's side (top). Two bridges cross "
        "the river, one on the left and one on the right; ground troops can only cross at a bridge, flying troops "
        "cross anywhere. Each bridge defines a lane: the left lane and the right lane. On each side, one princess "
        "tower guards each lane and the king tower stands behind them in the middle. Towers shoot enemy troops "
        "in range. A king tower does not attack until it is damaged or one of its princess towers is destroyed."
    ),
    "elixir": (
        "Elixir is the resource every card costs. You hold between 0 and 10. It refills on its own: one elixir "
        "every 2.8 seconds at the `single` rate, twice as fast at `double` (the last minute of normal time and "
        "the start of overtime) and three times as fast at `triple` (late overtime). Elixir at 10 stops "
        "refilling until some is spent: that is leaking elixir. While you sit at 10, the elixir you would have "
        "gained is lost for good, and the opponent keeps gaining theirs. The opponent has their own elixir, "
        "which is never shown."
    ),
    "elixir_and_strategy": (
        "Everything you do is paid for in elixir, so the elixir you hold right now limits what you can carry "
        "out. Playing a card costs its elixir at once. A strategy that takes several cards costs their total, "
        "spread over the time it takes to play them. Elixir spent on one thing is not available for anything "
        "else until it refills; saving elixir spends none. A card whose `elixir_cost` is more than the "
        "`elixir` you hold cannot be played until enough has refilled."
    ),
    "cards": (
        "Each player brings a deck of 8 cards. 4 are in the hand at any time and the next one to arrive is shown. "
        "Playing a card spends its elixir cost, puts it on the arena, sends it to the back of the deck order and "
        "brings the next card into the hand. A card is a troop, a building or a spell. Troops and buildings may "
        "only be placed on your own side — plus the part of the opponent's side next to a princess tower you have "
        "destroyed. A spell is cast on something of the enemy's: one of their troops, or one of their towers. "
        "A card you cannot afford is drawn greyed out and cannot be played."
    ),
    "card_types": {
        "troop": (
            "Becomes one or more units that move and fight on their own until they die. Most walk down the lane they "
            "were placed in toward the enemy tower, attacking what they are able to target on the way."
        ),
        "building": (
            "Stays where it is placed and acts from there: some attack what comes in range, some keep producing "
            "troops. Every building loses health over time until it disappears. Troops that attack only buildings "
            "walk to the nearest building, so a building can draw them away from a tower."
        ),
        "spell": (
            "An instant or short-lived effect on an area. It leaves nothing on the arena. It can be cast anywhere, "
            "including on the enemy's side, on enemy troops or enemy towers; with nothing of the enemy's in its area "
            "it does nothing."
        ),
    },
    "archetypes": {
        "win condition": "A card whose main purpose is to damage towers. It ignores or outlasts defenders to reach a tower.",
        "tank": "Very high health, low damage. Absorbs damage so the troops behind it survive. Strong against low-damage attackers; weak against tank busters and swarms that surround it.",
        "mini tank": "High health at a low cost. Holds a lane briefly or shields support troops. Weak against tank busters.",
        "tank buster": "Very high damage to one target at a time. Strong against tanks and mini tanks; weak against swarms, which soak up its single hits.",
        "high damage": "Deals a lot of damage per hit or per second.",
        "melee fighter": "A ground troop that fights up close, with no other speciality.",
        "splash": "Hits every enemy in a small area at once. Strong against swarms; weak against a single high-health target.",
        "swarm": "Many weak units. Strong against single-target attackers such as tank busters, which they surround; weak against splash and against spells.",
        "ranged support": "Attacks from a distance with low health. Strong behind something that protects it; weak when reached directly or hit by a spell.",
        "anti-air": "Able to attack flying troops. Troops without it cannot touch an air troop at all.",
        "air troop": "Flies. Only anti-air cards and spells can damage it; ground-only attackers ignore it.",
        "building targeter": "Attacks only buildings and towers and never fights troops. It cannot defend against troops.",
        "building": "A card that stays where it is placed and loses health over time until it disappears.",
        "defensive building": "A building that attacks enemies in range and draws building targeters toward itself.",
        "siege building": "A building that attacks towers from a long distance, from your own side.",
        "spawner": "Keeps producing new units for as long as it survives.",
        "cycle card": "Costs 1 or 2 elixir.",
        "small spell": "Cheap area effect with light damage. Strong against swarms and very-low-health troops; does little to anything with more health.",
        "medium spell": "Area damage that kills low- and medium-health troops such as ranged support. Does little to a tank.",
        "big spell": "Expensive, heavy area damage. Kills medium-health troops outright and takes a real share off a tower; still does little to a tank.",
        "utility spell": "A spell that does no real damage and changes the situation another way: freezing, speeding up, copying or moving troops.",
    },
    "tactics": {
        "elixir trade": (
            "Every fight is a trade of elixir: what you spent on your card against what the "
            "opponent spent on theirs. A trade is positive when the card you spent less on kills or "
            "outlasts the card the opponent spent more on; it is negative the other way round. "
            "Defending with the cheapest card that stops the threat, rather than the strongest one "
            "available, keeps trades positive and leaves you with more elixir than the opponent for "
            "what comes next."
        ),
        "overcommitment": (
            "Spending more elixir on a lane than the threat in it requires leaves you without "
            "elixir to answer whatever the opponent does next, including in the other lane. A "
            "single card that stops the attack is usually enough; adding more elixir on top of it "
            "is an overcommitment unless you mean to turn the defence into a counter push."
        ),
        "king tower activation": (
            "A king tower only starts shooting once it has taken damage or its own princess tower "
            "has fallen; once activated it fights alongside the remaining princess tower for the "
            "rest of the match. Letting a push reach your king tower is costly for this reason as "
            "well as the health lost. Activating the opponent's king tower, by the same token, adds "
            "a second tower to whatever is already defending their side."
        ),
    },
    "glossary": {
        "troop": "A card that becomes one or more units which move and fight on their own until they die.",
        "building": "A card that stays where it is placed, acts from there, and loses health over time until it disappears.",
        "spell": "A card with an instant or short-lived effect on an area. It leaves nothing behind to fight. It is cast on enemy troops or enemy towers; with none in reach it has nothing to affect.",
        "lane": "One of the two paths (left, right) that run from your princess tower, over a bridge, to the enemy princess tower.",
        "bridge": "The crossing over the river in a lane. A troop placed at your end of a bridge reaches the enemy side fastest.",
        "princess tower": "One of the two outer towers on each side, one per lane.",
        "king tower": "The central tower at the back of each side. Destroying it ends the match.",
        "pocket": "The area on the opponent's side beside one of their princess towers, which opens to your troops once that tower is destroyed.",
        "push": "A group of your troops advancing down a lane toward the enemy tower.",
        "counter push": "An attack made with troops that survived defending, continuing forward in the same lane.",
        "win condition": "A card whose main purpose is to damage towers, for example because it only targets buildings.",
        "tank": "A card with very high health that absorbs damage, shielding the troops behind it.",
        "mini tank": "A cheaper card with high health.",
        "ranged support": "A troop that attacks from a distance and usually has low health.",
        "swarm": "A card that deploys many weak units at once.",
        "splash": "Damage that hits every enemy in a small area rather than a single target.",
        "targets": "What a card is able to attack: ground only, air and ground, or buildings only (towers count as buildings).",
        "flies": "A flying troop ignores the river and can only be attacked by cards that target air.",
        "cycle": "Your 8 cards come back to your hand in a fixed order as you play them; `next_card` is the one that arrives next. Cycling is playing a card you hold in order to bring the next card into your hand.",
        "elixir leak": "Elixir lost by sitting at the 10 cap, where nothing more refills.",
        "health_remaining": "A unit's or tower's current health as a fraction from 0 to 1.",
    },
}
