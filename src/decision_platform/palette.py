"""The validated chart palette and offer identity, with no UI dependencies.

Shared by the Streamlit design system, the Power BI export and the generated report,
so an offer is the same colour on every surface. The categorical slots were validated
for colour-vision deficiency on the navy surface #0d2030 (worst adjacent CVD delta-E
8.4, normal vision 19.3, every slot at least 3:1 contrast).
"""

from __future__ import annotations

# Categorical slots, fixed order: blue, orange, aqua, yellow, magenta, green, violet, red.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
NEUTRAL = "#5b7486"
INK = "#081522"

# Nine offers, eight validated hues: the two loyalty-point rewards are one mechanic at two
# sizes, so they share the violet slot and are told apart by label and by texture (the
# larger reward is hatched). Every ninth hue tried fails the normal-vision floor against
# the slot it would sit beside, so a generated colour is not an option.
OFFER_COLORS = {
    "rush_hour_25": SERIES[0],
    "offpeak_15": SERIES[1],
    "pct_10": SERIES[2],
    "weekend_20": SERIES[3],
    "spend_10": SERIES[4],
    "free_trip": SERIES[5],
    "loyalty_500": SERIES[6],
    "loyalty_1500": SERIES[6],
    "offpeak_pass": SERIES[7],
}
OFFER_TEXTURE = {"loyalty_1500": "/"}


def offer_color(offer_id: str) -> str:
    return OFFER_COLORS.get(offer_id, NEUTRAL)


def offer_fill(offer_id: str) -> str:
    """CSS background for an offer swatch or share bar, hatched where the slot is shared.

    No quotes and no semicolons, so it can sit inside a single-quoted HTML style
    attribute that is itself inside a DAX string.
    """
    color = offer_color(offer_id)
    if offer_id in OFFER_TEXTURE:
        return f"repeating-linear-gradient(45deg,{color} 0 4px,{INK} 4px 6px)"
    return color
