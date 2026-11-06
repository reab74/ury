# Regnosa unified POS extension — stage 2A

Flora owns arrangement business logic. URY supplies a small optional invoice-item
extension point plus cart row metadata. ERPNext core remains unchanged.

The maintained deployment/acceptance record is `docs/operations-and-release.md`
in the `reab74/flora_pos` repository, branch `feature/regnosa-unified-pos`.

## Extension contract

`ury_invoice_item_resolvers` is a Frappe hook list. Each callable receives an
item payload and trusted server context (`pos_profile`, `price_list`, `branch`,
`menu`). Return None for an ordinary Item, or a server-validated invoice-item
dictionary for a custom Item. Multiple non-None resolutions are rejected.
An unresolved `custom_flora_arrangement` reference fails closed. Ordinary Items
still go through the existing Item Price logic; the client rate is not trusted.

The Flora resolver validates its own roles, configuration, prepared Item/Repack
and amount. This stage is manager-only; settings remain disabled, and the Flora
stage-one invoice submission guard stays installed.

Arrangement cart keys use preparation identity instead of Item Code. The actual
reference is transported in `custom_flora_arrangement`, never inferred from a
cart key, comment or Item name. The standard bill-split copier carries that
reference, but splitting and reservation lifecycle acceptance remain pending.

## Tests and build

```bash
python tests_offline/test_invoice_item_extensions.py
python tests_offline/test_kot_access.py
node tests_offline/test_arrangement_cart.cjs
```

These are isolated behavioral checks, not browser/accounting integration tests.
The Node harness runs the actual store with small Zustand/storage doubles and
uses built-in TS stripping or the project's existing TypeScript dev dependency.

Build the installed app with `bench build --app ury` from the bench directory.
No new package dependency, generated asset edit or ERPNext core change is needed.

Source baseline supplied: `a03947c`. Full frontend build and live acceptance must
be recorded on the test VPS. Do not enable arrangement sales at stage 2A.

## Stage 2B — manager lifecycle guards

Flora baseline `f9db534`; URY baseline `d3d3e34`. The arrangement lifecycle now
reserves saved drafts, completes POS sales and validates consolidation, while
Regnosa's settings remain disabled pending live acceptance and cashier UI work.

Optional `ury_before_order_cancel` and `ury_before_bill_split` hooks receive the
loaded invoice (plus `items_to_move` for splitting). They run before side effects.
Flora blocks unsupported arrangement cancellation/refunds/transfers. Cancellation
is guarded before the existing URY table-release/commit path. The old unrelated
URI draft cancellation implementation is not repaired in this patch.

Item reduction permission checks distinguish arrangement references as well as
Item Code. Replacing one preparation with another of the same Item Code cannot
hide removal of the original. Ordinary Item quantity aggregation is preserved.

These are backend-only changes. No frontend build is required in this stage.
Continue running both offline Python suites and the existing Node cart harness;
run each Flora suite separately. Use the Flora operations guide for deployment,
acceptance limits and the next test-site checkpoint. Do not enable cashiers yet.

## Stage 3 — arrangement dialog, manager preview

Baselines: Flora `1a4cef4`, URY `58afbdf`. Optional `ury_pos_features` providers
return UI feature metadata after the current profile access check. Flora exposes
`flora_arrangements` to assigned System Managers on configured URY profiles.
No new dependency or permission assignment is introduced.

The toolbar opens a searchable existing/new finished Item selector, components,
price and notes. Saved Draft/Repacked arrangements can be resumed separately.
Save Draft consumes no stock; Prepare & Add calls Flora's controlled API, retains
the saved ID after failures, and verifies the destination tab/profile before add.
Settings remain disabled during preview, so preparation cannot be invoked in UI.

English, French and Arabic text is included. Full Vite build and browser checks
must run on the VPS; local frontend dependencies were unavailable. No schema
changes are included, so this stage needs an asset build, cache clear and shared
service restart, but no migration. See Flora's operations guide for acceptance.

## Material cost display / Item search clarification

The builder displays its configured finished Item Group/UOM and an explicit
search/no-match state. Eligibility is unchanged; an expected Item Code must be
checked before changing any group selection policy or shared Item master.

Manager preview estimates use Flora's configured raw-material warehouse. Unit,
row and total values are estimates; absent valuation remains Unavailable. No
estimated rates are sent into draft or stock-entry payloads. Node tests cover
zero versus unavailable, quantity multiplication and incomplete totals. Build
and live cost display checks remain required; preparation stays disabled.

### Live verification — 6 November 2026

Zero-sales session closed successfully with explicitly entered zero amounts.
Arrangement FL-ARR-00020 used existing Item REG-TEST-ARR-001.
Repack MAT-STE-2026-00028 consumed 20 roses and 1 packaging:
total valuation QAR 105, one finished unit produced.
Draft POS Invoice REG-00013 reserved the arrangement and preserved its row link.
Cash payment QAR 150 submitted the invoice and completed the arrangement.
POS closing consolidated into submitted Sales Invoice ACC-SINV-2026-00036,
with update_stock 1 and the arrangement reference preserved.
Verified finished-item stock movement -1 and remaining quantity 0.
Mixed orders, concurrency and general cashier permissions remain unverified.

### Mixed-order verification — 6 November 2026

REG-00014 combined REG Test Tea at QAR 10 with arrangement
FL-ARR-00021 / REG-TEST-ARR-001 at QAR 50.
Arrangement preparation linked to MAT-STE-2026-00029.
Draft reservation and arrangement row identity were verified.
Cash payment QAR 60 submitted the invoice, outstanding 0,
and completed the arrangement.
Closing created submitted Regnosa Sales Invoice ACC-SINV-2026-00037.
Both item lines and the arrangement reference were preserved.
Verified arrangement stock movement -1.
No tea stock movement was returned; tea stock configuration and
ingredient consumption have not been verified.
Concurrency and operation without System Manager remain unverified.
