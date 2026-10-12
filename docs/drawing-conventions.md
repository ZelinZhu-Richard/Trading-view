# Drawing conventions and verification

The 24 tools render through a Lightweight Charts `ISeriesPrimitive` attached to
 the price series. They share time/price anchors, selection and hit testing, pointer
creation, anchor or whole-object dragging, an OHLC snap option, styling, object-list
management, and per-chart undo/redo. Undo history retains up to 100 complete actions
in the running browser; saved geometry and style survive restart. Undo history
itself is not currently stored across restarts.

The public reference investigation could not establish drawing-edit behavior behind
its sign-in prompt. The implementation uses the documented primitive lifecycle and
explicit app conventions; it does not claim pixel or behavior parity with TradingView.
See `reference-ledger.md` (REA-03) and the [official primitive documentation](https://tradingview.github.io/lightweight-charts/docs/plugins/series-primitives).

- Anchors are UTC timestamps and positive prices. Missing exact chart timestamps
  are interpolated for presentation; the saved anchor does not change when chart
  intervals, size or view range change. All drawings belong to an instrument.
- Lines, rays and extended lines clip to the price pane. Regression channels fit
  source closes over the selected bar range, with population residual standard
  deviation and bands at ±2 standard deviations. The fit is descriptive and can
  change when the selected source interval/history changes; it is not strategy input.
- Fibonacci levels are calculated in price space, then projected to screen space.
  The retracement's first anchor is level 0 and second is level 1. Extensions use
  the first-to-second price move at the third anchor. Levels are explicitly editable.
- Brush is one pointer gesture. Path uses successive clicks and Enter/double-click
  to finish. Escape cancels an unfinished drawing. Picking a selected anchor edits
  that anchor; picking another stroke moves the whole object.
- Position drawings take entry, stop, target anchors in that order. `backend/money.py`
  rounds prices to the nearest tick, half up, and quantity toward zero to its step.
  It calculates gross risk/reward in the instrument quote currency, with no fees,
  slippage, currency conversion or actual order. Invalid stop/target sides show an
  error. The future simulation engine must reuse these precision functions.
- Measurements use elapsed UTC time, signed price difference/percentage and the
  source-bar count within the selected endpoints. Weekends are not subtracted from
  elapsed calendar time.

## Actual verification

`src/drawingGeometry.test.ts`: 28 cases cover all tool families, finite geometry,
clipped lines, degenerate hit tests, nonlinear Fibonacci projection and a manually
derived regression fixture. `tests/test_money.py` covers decimal tick/quantity
rounding, long/short risk/reward and invalid orientation.

`evidence/browser/drawings-report.json` records Chrome on macOS pointer creation
of all 24 families, persisted anchors, anchor dragging, complete-action undo/redo,
label/style change, lock, hide/show, duplicate/delete and reload. Screenshots are
`drawing-objects.png` and `drawings-all-families.png` in the same directory.

Still to verify: whole-object movement and snapping against independent coordinate
expectations, locking during attempted drag, interval-change/resize placement,
all keyboard interactions and cross-browser/platform coverage. The full product
acceptance goal remains open.

## Keyboard and coordinate entry

**Drawing objects → New drawing type → Create drawing** initializes the selected
family at recent visible source bars. Edit UTC coordinates, appearance and label,
then save. This creates the same stored objects and undo history as pointer tools.
Paths/brushes support adding/removing vertices and paging through all anchors in
sets of 100. The form is also available for locked objects. Dialogs return focus
to their opening control when closed. Focus a chart to pan with left/right arrows,
zoom with +/- and fit with Home. The source data table provides text values.
The in-app keyboard verification is in `../evidence/browser/keyboard-report.json`;
full Chrome/Edge keyboard acceptance remains separate.
