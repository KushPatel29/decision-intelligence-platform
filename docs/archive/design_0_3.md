# Corridor campaign workspace, release 0.3

Subject: a simulated toll-road campaign desk for customer, revenue and transportation analysts. The first job is to review a feasible campaign; the second is to change its limits and compare the result.

## Tokens and composition

- Harbour ink `#081522`: workspace. Deep channel `#0d2030`: navigation and panels. Signal teal `#4bdcd5`: the chosen allocation. Transit blue `#61a9ec`: baseline demand. Reserve amber `#ffc773`: protected capacity and review. Frost `#eef8ff`: primary type.
- Bahnschrift gives headings the character of transport signage; Segoe UI carries controls and explanations. Tabular figures support comparison. No remote fonts or image dependencies.
- Left-aligned navigation and page headings. One wide corridor schematic is the signature element, with six labelled zones and capacity rings derived from the actual planning data. Campaign outcomes belong to that same panel, rather than four detached decorative cards.
- Overview, Scenario studio and Decision evidence separate the three jobs. A quiet resource ledger explains budget, contacts and reward limits. Scenario templates remain editable, and results show changes against the saved baseline.

```
Corridor navigation | Decision centre              Simulation / Oct 2025
                    | October campaign / saved baseline
                    | West --- Northwest --- Central --- ... --- Outer east
                    | expected trips | net contribution | spend | contacts
                    | Overview / Scenario studio / Decision evidence
                    | activity + offer mix / resource ledger
```

## Review before building

The previous oversized promotional headline and repeated uppercase labels could fit almost any analytics product. Replace them with the campaign date, actual allocation, named corridor zones and capacity information. Keep the requested futuristic atmosphere in the transport schematic and signal palette; omit gradients, animated telemetry and generic AI claims. The corridor is schematic, not a geographic map or a live feed.

Use actual weighted utilization (sum of forecast plus allocated trips divided by sum of capacities), with reserve separately labelled. Do not average unlike capacity cells or present unused capacity as unused budget. Every threshold and comparison retains a text label. All outcomes remain explicitly simulated.

The compact outcome rail wraps to two columns on narrow screens. Native controls retain keyboard semantics; focus is visible and reduced motion is respected. Avoid changing Streamlit widget labels or hiding the contents of data tables to achieve a visual effect.

## Final review

Chrome review confirmed the campaign view at the native desktop size and a 390-pixel viewport. The page stays at 390 pixels wide, the outcome rail uses two columns and the corridor scrolls within its own panel. Scenario controls stack vertically and retain their labels. The narrow view explicitly explains how to scroll the corridor. The primary form button uses dark text on teal; keyboard focus uses amber.

The new Lean budget template solved in Chrome with 100 contacts, CAD 799.61 incentive costs against an 800 budget, CAD 1,710.74 expected net contribution and 154.0 expected additional trips. Automated coverage exercises all ten workspaces, the free HiGHS solver, real Gurobi solves, templates, comparison history, zero spending and zero reward limits. Capacity display tests cover unequal cell sizes and replacement of baseline allocations. The full suite contains 46 passing checks. These figures describe expected simulation outcomes.

Removed an overly broad CSS gap override after it made native metric columns wrap. Preserved Streamlit's own responsive column sizing. Cleared the persistent app header with measured spacing; labels and state text now remain readable at the top of the workspace. No non-user-triggered animation is used.
