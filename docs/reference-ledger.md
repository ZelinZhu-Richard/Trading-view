# Reference behavior ledger

## Scope and provenance

Reference: [TradingView Supercharts](https://www.tradingview.com/chart/), observed **2026-10-11, 23:40–23:51 UTC**. Access was a public, unsigned, isolated browser profile; no account, purchase, broker connection, or order was used. Browser: Chrome 155.0.8059.39, headless, viewport 1440 × 960. Exact target: `56FB732BC18BCB84E64A5779DAE93BE1`; owned loopback endpoint during this observation: `http://127.0.0.1:60681`. The endpoint is session-specific, not a permanent configuration.

Playwright performed ordinary UI actions. **REA passively captured the resulting accessibility/DOM state and viewport pixels.** REA did not click, navigate, execute page JavaScript, or capture activity before attaching. Nothing observed here is a market-data feed for the application.

Retained artifacts (raw bundles, logs and screenshots remain local; see the
[evidence publication notes](../evidence/README.md)):

- Local `evidence/tradingview-reference.json`: 37 complete retained Evidence records from this investigation, including screenshot bytes and provenance.
- [Evidence index](../evidence/tradingview-reference-index.json): timestamps, authority, confidence, completeness, limitations, and screenshot hashes.
- Local `evidence/reference-baseline.json`: the parent's earlier target discovery and baseline records; separate REA session.
- Local `evidence/reference-actions.jsonl`: successful Playwright actions and their immediate accessibility snapshots. Actions are not REA Evidence. Some snapshots precede asynchronous UI completion; the later REA captures are the authoritative observed states.
- `evidence/screenshots/`: 16 unmodified PNG artifacts decoded from the bundle, verified against each recorded byte count and SHA-256.

All REA page inspections retain `policy_filtered`/`attach_limited` qualifications: only the selected origin and attach window are covered. Script sources, credentials, storage values, and raw response bodies were not requested. Screenshots cover only the visible viewport. The external service has no local shipped-artifact digest; these observations do not establish its implementation, numerical algorithms, backend behavior, or behavior on another account/platform.

## Investigation checklist

| ID | Question | Outcome |
|---|---|---|
| REA-01 | Symbol, interval, zoom, crosshair | Answered within the observed single-chart workflow |
| REA-02 | Indicator addition, settings, visibility, panes | Partially answered: catalog, existing-volume settings and hide/show observed; addition and pane movement unresolved |
| REA-03 | Drawing creation, anchors, style, selection, deletion | Partially answered: catalog and explicit sign-up gate observed; manipulation inaccessible |
| REA-04 | Watchlist organization and chart selection | Partially answered: menu, grouped rows, and chart selection observed; section creation requires sign-in |
| REA-05 | Panel resizing and chart layouts | Partially answered: resize, collapse, editor docking and layout menu observed; multi-chart runtime requires upgrade |
| REA-06 | Replay and strategy-result workflows where accessible | Partially answered: replay gate and editor observed; replay execution and reports inaccessible |

These outcomes describe reference coverage, **not implementation completion or verified parity**. Application verification cases below are requirements to execute against Market Workbench, not tests that have already passed.

## REA-01 — Chart navigation

**Reproduction.** Open the top interval button on AAPL daily; choose `1 week`. Move the pointer into the chart. Open the symbol button, search `TSLA`, and press Enter after search results settle. Subsequently select NFLX from the watchlist. With the watchlist collapsed, capture the NFLX weekly view, move to `(750,350)`, then send a vertical wheel delta of `-1200` and capture again.

**Observed.** The interval menu groups ticks, seconds, minutes, hours, days, and ranges; each item has a favorite action, and the current interval is selected. Choosing weekly changes the toolbar and chart title to `1W` and exposes `Undo change resolution`. The search dialog accepts symbol/ISIN/CUSIP, offers asset-type tabs, and lists multiple exchange/instrument matches. Selecting TSLA changes the chart title, instrument details, and selected watchlist row while retaining weekly resolution. Crosshair position has horizontal price and vertical date labels; the top OHLC and volume readouts follow the pointed bar. In the paired NFLX zoom captures, negative wheel input expands candle spacing and reduces the visible date span. A tooltip explains that holding Command while zooming maintains chart position; that modifier behavior itself was not tested.

**REA Evidence.**

- Interval menu: `ev_6930f2309067ae5d9168755ec60ff8a522d44582fcc71a8ce10cd0d7701886e4`.
- Weekly AAPL/crosshair pixels: `ev_d907a1e5e07519f1f0618c025a0b5ae1bee238e261c8218419410a137c6aa3ad`.
- Symbol search: `ev_f37a2ae4194b9742b96237d335fff0b473a444b61142cbbbf0dde4eadf7edbd9`.
- Selected TSLA: `ev_3be9181aa8c8176803f75a2896edd743b9aab0a8e0cbf6f5bef905add439118a`.
- Matched NFLX zoom pair: `ev_cf7798b082dada35d451bc34d16687c2973d2facb54c94eb5157d50d25292d55` → `ev_3e348a1a19e11ac8c35cc1ec657e08eebab56f8529653f5cbeb41cb91cbc6169`.

**Limits/inference.** The first wheel attempt did not establish a change because the helper had not moved its current pointer into the chart; do not use `ev_434477ac42d2eb8e33a58314616b7785c2830ea70c7ba5198765821671b6d840` as evidence of successful zoom. No exact zoom transfer function, all-interval data coverage, keyboard navigation coverage, or multi-chart synchronization was established.

**Application behavior and checks.** Keep canonical instrument identity separate from display labels; show market/provider beside ambiguous symbols. Preserve per-chart interval across symbol changes only when supported, otherwise visibly explain the capability constraint. Test selecting a same-ticker/different-exchange result, cancelling stale data responses, crosshair OHLC consistency, wheel zoom, fit/reset, and linked-chart propagation without loops. Capability gating is an application design requirement, not a claim about the observed reference menu.

## REA-02 — Indicators

**Reproduction.** Open `Indicators, metrics, and strategies`, search `Relative Strength Index`, and select the built-in result. Close the menu. Later, return to the chart, hover the visible `Vol` title at approximately `(70,124)`, select its settings icon `(130,124)`, inspect Inputs and Style, and cancel. Hover the title again and toggle the eye icon off, then on.

**Observed.** The catalog separates built-in technicals from community entries and provides indicator/strategy-related tabs. Search returns built-in RSI alongside separately attributed community scripts. RSI did not appear on the chart in this session; a generic join prompt subsequently covered the page. This temporal sequence does not establish that every indicator is gated or that this particular generic prompt was caused by RSI selection.

The existing volume legend reveals hide, settings, remove, and more controls on hover. Its settings dialog has **Inputs, Style, Visibility** tabs. Inputs exposes MA Length and a previous-close color option. Style exposes Volume and Volume MA visibility, growing/falling styling controls, precision, scale labels, status-line values, and input-value display; Defaults, Cancel, and Ok are available. Hiding volume removes its histogram while retaining the legend with a crossed-out eye; the toolbar offers `Undo hide Vol`. Toggling again restores volume and changes the undo description to `Undo show Vol`.

**REA Evidence.**

- Search results: `ev_11ccd2b30f5fb2bc12d659734552d56226bf25878a3e341c37360c19ff0b2fbd`; pixels `ev_f23ce0ca57ccc45f884a8d540cad26dbe39318f8e3b24f6e2b5252dacfbc77ba`.
- Generic join overlay: `ev_b4085a28377d808f9ea93ac35affe522f7f313ea6745302fd8ad892ca3522b76`.
- Hover actions: `ev_b0799a6060e3a0512d3e89171e1d589526054b9cc1fd2e5f13455f274a752e9c`.
- Settings Inputs: `ev_9df7c32f5fd88f29370e54d5f5523c657b79582ba58a341450020cf5613e4fdf`.
- Settings Style: `ev_22b4fe033e82f4e8af19a532922fcdb653a3a7848aadf242c6457d4e78d78c16`.
- Hidden-volume pixels: `ev_1256f775bc7f71c9746dc2f7007579b719c6d25ad8d409863a2a2685de148ff9`.
- Restored volume and undo action: `ev_113428d25a861996a9fb434797af8340279393fbb738c761ee79f0e6856042df`.

**Limits.** Early locator attempts targeted hidden/covered legend elements and did not open settings. The later coordinate-based hover/selection produced the actual dialog. Settings were inspected, not numerically changed. No indicator formula, warm-up convention, new RSI pane, pane move, or indicator persistence across account sessions was verified.

**Documentation fallback, read 2026-10-11.** TradingView describes [settings beside the indicator title](https://www.tradingview.com/support/solutions/43000480333-how-to-adjust-the-indicator-settings/) and [hover-revealed actions](https://www.tradingview.com/support/solutions/43000539711-how-to-show-hide-settings-and-remove-options-of-an-indicator-or-ticker-symbol/). Its [pane-management help](https://www.tradingview.com/support/solutions/43000482922-how-to-place-two-indicators-on-one-pane/) describes a Move To context-menu option and mouse movement between panes. Pane movement is documentation-derived here, not observed runtime behavior.

**Application behavior and checks.** Provide discoverable settings and keyboard-accessible equivalents to hover controls. Separate calculation inputs from display styles and visibility; preserve indicator identity when hiding or moving it. Verify add → edit parameters → change pane → hide/show → undo → reload; each step must retain the intended values, settings, scale assignment, and causal warm-up gaps. Use independent numerical tests rather than treating reference pixels as numerical validation.

## REA-03 — Drawings

**Reproduction.** On TSLA weekly select Trendline, click the chart at `(350,450)`, then attempt the second anchor `(650,300)`. Close the resulting prompt. Open `Trend tools` to inspect the catalogue.

**Observed.** The first placement attempt opens an explicit prompt requiring a free account for trendline and the other drawing tools; no line was created. The visible tool menu groups line tools, channels, and pitchfork variants and includes favorites/help affordances. The toolbar separately exposes magnet snapping, keep drawing, locking, hiding, and removal controls. A Trendline tooltip mentions a Shift constraint at 45 degrees; the constraint was not exercised because placement was gated.

**REA Evidence.**

- Placement gate: `ev_424f75d0bcb08ba07014dea3ae3c8fce1bb332b6cf8c93e7d46ea99bee6cce5b`; pixels `ev_29f2a913f372d7bb9ae221a9cd7bc7fd60cadb5c1429936be735b9243193f670`.
- Trend-tools catalogue: `ev_a44d4beb56ab5b12916520b079266972edad8cd6b5f84140a7218339b53a825a`.

**Limits.** Anchor creation/editing, selection hit testing, styling, deletion, persistence, snapping tolerance, and undo semantics remain unobserved. Promotional video imagery inside the gate is not evidence that the corresponding tool was executed in this session.

**Documentation fallback, read 2026-10-11.** The official [Trendline guide](https://www.tradingview.com/support/solutions/43000518095-trend-line/) describes color/opacity/thickness/style, endpoint arrows, point-price labels, text formatting, and exact endpoint placement using bar and price coordinates. It also describes interval visibility settings. These capabilities inform design; they do not establish the reference's internal storage schema.

**Application behavior and checks.** Store drawing anchors in chart-domain coordinates, not pixels. Expose selection handles, numeric coordinates, style/label controls, lock/hide, duplicate/delete, object list, and undo/redo. For each required drawing family, verify creation and edits, zoom/pan/resize alignment, coordinate round trips, snapping, and reload. Test cancellation before the last required anchor and editing after interval changes. The unified model and exact persistence format are application design choices.

## REA-04 — Watchlists

**Reproduction.** Open the watchlist name menu; choose Add section and observe its result. Close the sign-in prompt. Click the existing NFLX row.

**Observed.** The starting watchlist has market sections and Symbol/Last/Chg/Chg% columns. Its menu exposes share, list alert, copy, rename, add section, clear, create, upload, and open actions. Add section opens a sign-in dialog; no section was created. Selecting NFLX changes the chart to Netflix weekly and refreshes the right-side instrument details. The selected row has a clear outline in addition to price-change colors.

**REA Evidence.**

- Management menu: `ev_e38c64d1db234a9d6e78c32046f26b17c5615843ba5e173b6572b6939b4ce935`.
- Add-section sign-in: `ev_586385dc5d02f59c44f0d278f7d18a5fdf29078c3bef0de3e08a0676f2e2c4ce`.
- NFLX selection: `ev_99075076c89360f0c75ddab7f660a01489cc75088c247a16c1bd00a16045194e`.
- Selected-row pixels: `ev_af68d8931bc6a38cc1e94ac074438a228bb77e9c989ce1091845e45ea5673b08`.

**Limits.** Creation, reorder, rename, import/export, account synchronization, and list-alert execution were not verified. A visible menu action is not proof that its flow succeeds.

**Documentation fallback, read 2026-10-11.** [Mastering watchlists](https://www.tradingview.com/support/solutions/43000745825-mastering-the-tradingview-watchlists/) describes adding symbols through search, dragging rows into sections, sorting by column headers, and managing sections from the list menu. [Section help](https://www.tradingview.com/support/solutions/43000615520-how-to-add-a-section-to-the-watchlist/) also documents a selected-row context menu. These organization workflows remain documentation-derived.

**Application behavior and checks.** Treat watchlist membership, manual order, sections, and selected chart symbol as distinct persisted state. Verify create/rename/delete list, add/remove/reorder instrument, duplicate suppression, manual-order restoration after sorting, section edits, and keyboard chart selection. Ensure provider identity and stale/unknown values remain explicit when rows cannot quote.

## REA-05 — Layouts and panel sizing

**Reproduction.** Open Layout setup on NFLX weekly; inspect layout thumbnails and sync switches. Choose the `2h` menu item. Close the upgrade prompt. Drag the chart/watchlist boundary from `(1092,500)` to `(980,500)`, then collapse Watchlist through its right-rail button. Open Pine and select Move overlay to split-view.

**Observed.** The layout menu offers grouped chart arrangements and separate sync switches for Symbol, Interval, Crosshair, Time, and Date range; the single-chart session shows these switches disabled, with Crosshair checked. Selecting the two-chart arrangement opens an upgrade prompt explaining the current one-chart limit. Dragging the side boundary widens the watchlist and narrows the chart. Collapsing it gives the chart the freed width. Pine first opens over the right side; split-view reserves its own width and resizes the chart. A subsequent ordinary page reload retained the NFLX weekly selection and the editor's split-view state in this isolated browser session.

**REA Evidence.**

- Layout menu: `ev_bbe027d1373670943b55d7c3e55b3914ad5ee0f5a895a7f0fa3e8afdd3a99129`; pixels `ev_00ddcb67e21dc6f348c2f0e2e5154a13bab69ae436ddbccd00a24421381c305f`.
- Two-chart upgrade gate: `ev_6a915fd70ff9cbcde9353c699bc1402576b6a3fab94159a35fc8f704922bfbaf`.
- Resized side panel: `ev_af68d8931bc6a38cc1e94ac074438a228bb77e9c989ce1091845e45ea5673b08`.
- Collapsed side panel: `ev_791e4c4f126249ba91481b65aa3f831174f27fc2968d6cb10d003e80fc573842`.
- Editor overlay → split-view: `ev_c14454df851a861bfaaba2df25290d38fd3e1bdbc75a84712803caf42370b954` → `ev_6453171d1dff3166411add4b6eb52c718eaa4fd88f0662b49f637c031811f871`.
- Reloaded split-view state: `ev_e90791a31c1c518eaccb9080d4b5f5545d346acd16616a04928a525f9ce2a7be`.

**Limits/inference.** This does not prove multi-chart sync implementation, cross-device persistence, durable account saves, exact minimum widths, or persistence after a full browser restart. Observed reload retention could be local browser storage; the storage mechanism was not inspected. Market Workbench's required bottom research panel remains the user's chosen layout even though this reference version exposes a right-side editor.

**Application behavior and checks.** Use container-size observation to update charts after split or collapse. Test one/two/four charts, independent sync toggles, panel minimum sizes, collapse/restore, and restart persistence at 1280 × 800 and 1920 × 1080. Verify that active chart selection is explicit and linked updates do not recurse. Multi-chart functionality is required by goal.md independently of the reference gate.

## REA-06 — Replay and research results

**Reproduction.** Click Bar replay. Record and close the sign-up prompt. Open Pine from the right rail and inspect the editor and docking controls. Attempt to open its script menu; the session is subsequently covered by the generic join prompt.

**Observed.** Replay opens an explicit free-account prompt; no replay timeline or stepping session is available. Pine exposes an untitled editor, Add to chart, Save script, Publish script, and position/version status. It can switch between overlay and split-view. No script was published, no custom strategy was run, and no result report was displayed.

**REA Evidence.**

- Replay gate: `ev_6b0246705de75f6ae8284366024f5521373702b0d9ac3d6d3dfe7ae249805312`; pixels `ev_ad233a9ad2a08b56cae087783fd1878d64bf5a9e2476493e9ed43ac074d74b1e`.
- Editor: `ev_63736f11ac881d618fb9450afbcff2a8ebc86c44262ed1797ae31a1b0341fc33`.
- Generic join-overlay limitation: `ev_d473bdf862d84522e2c46b0e581b0383213263e424432af6a13668aa27c733d3`.

**Documentation fallback, read 2026-10-11.** [Replay activation help](https://www.tradingview.com/support/solutions/43000474024-how-do-i-turn-bar-replay-on/) describes selecting a historical start, play and speed controls, selecting one or all charts, and returning to the current chart. It also distinguishes replay bars from live quote/order/alert behavior. This is a reason for Market Workbench to make historical versus live state conspicuous, not to copy those execution rules.

The official [Strategy Report guide](https://www.tradingview.com/support/solutions/43000764138-tradingview-strategy-report-how-to-start/) describes automatic report opening after strategy addition, equity and drawdown metrics, and a trade table containing execution time, price, size, and P&L. Report layout and behavior are documentation-derived; no report was observed here.

**Limits.** Reference fill rules, replay cutoff enforcement, strategy computation, metrics, multi-symbol portfolios, report exports, and engine determinism are unknown. A marketing preview inside the gate is not a working replay capture. Pine is only a reference workflow; Market Workbench uses Python as specified.

**Application behavior and checks.** Provide an explicit simulated clock, start/step/play/pause/speed controls, reproducible run IDs, and reports linked to snapshot/script/settings hashes. Test that replay reveals no future bars, repeated runs match, every trade reconciles to portfolio cash/positions, currency conversions are causal, and exports agree with the displayed report. The shared engine and portfolio rules come from goal.md and require independent accounting and causality tests.

## Remaining reference work

The public pass has answered the bounded accessible questions and recorded concrete limits. Further runtime evidence for indicator addition/pane movement, drawing editing, watchlist organization, multi-chart synchronization, replay execution, and strategy reports would require suitable user-provided authenticated access and, for the observed multi-chart gate, an eligible plan. No such access was requested or changed. These gaps must not block unrelated implementation or be converted into parity claims. Use the documented behavior and goal.md choices above until additional reference evidence is available.

## Implementation verification cross-reference — 2026-10-12

The observation records above remain unchanged. Corresponding application checks
now exist in `../evidence/browser/chrome-final/` and `../evidence/browser/edge/`,
with drawing edge checks also in `../evidence/browser/edge-drawing-edges/`.
`requirements.json` maps reference subjects R095–R107 and each implemented behavior
to current evidence. These application checks do not remove the reference session's
sign-in/upgrade gates or imply behavior that REA could not observe.
