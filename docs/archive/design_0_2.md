# Corridor 2.0 design direction

Audience: an analytics leader reviewing proposed customer incentives and roadway headroom. The first screen should explain the decision, its expected value and its evidence in one glance.

Direction: a transportation control room. A bespoke vector corridor anchors the opening screen; compact status badges, aligned numerical cards and interactive capacity charts support the decision. Avoid a generic dashboard wall of equally weighted cards. Put review and scenario actions after the recommendation.

Palette: Midnight #081522, Harbour #102437, Slate #233C52, Signal cyan #4BDCD5, Iris #9399FF, Amber #FFC773; text #EEF8FF. Cyan means a recommendation, amber means uncertainty or limited headroom. Use sufficient text contrast. Avoid using colour alone to communicate status.

Typography: Bahnschrift for the brand/display on Windows, Segoe UI for controls and body; system fallbacks elsewhere. Tabular numbers, restrained uppercase labels, large main headline and readable explanatory text. No remote fonts required.

Layout: narrow persistent navigation, 1560px maximum content width, asymmetric hero with corridor graphic, four outcome metrics, interactive activity chart beside a constraint summary. Secondary pages use the same hierarchy with a focused analytical chart and an exportable workbench.

Interaction: real Gurobi/HiGHS scenario solves with budget, contacts, ROI, reward liability and capacity reserve controls. Saved scenario comparison supports review; the app never sends offers. Rich hover details, resettable filters and downloadable evidence. Motion is limited to a subtle signal indicator and disabled when reduced motion is requested.

Quality gates: native Streamlit controls remain keyboard accessible; explanatory uncertainty remains visible; every page is exercised; test narrow viewport and browser rendering. Keep the portfolio simulation label on every page.
