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


### Draft order cancellation correction — 11 November 2026

The live cashier Cancel action on an ordinary tea draft failed because cancel_order
called Document.cancel() before its draft/submitted branch, then contained a second
cancel call and direct docstatus writes. The test draft was subsequently deleted
through the Administrator's normal deletion hooks; no live patch verification yet.

Draft cancellation now retains the invoice with docstatus 0 and operational status
Cancelled, reason and an audit comment. It neither submits nor forces docstatus 2,
and retains the POS Invoice identity used by KOT company/profile checks. Active
order and table lookups exclude these voids. A persisted void cannot be edited,
submitted, paid or reopened through normal saves or the controlled order paths.
This operational state is intentionally distinct from a submitted accounting
invoice cancelled through ERPNext. Submitted ordinary invoices use cancel() once;
consolidated invoices, returns and merged bills fail closed. Arrangement cancellation
remains blocked by Flora's existing guard until its supported workflow exists.

Cancellation is POST-only, locks the invoice, checks invoice cancel/read rights,
profile/company/branch and existing ownership/room rules, and requires draft write
rights. It commits nothing itself. KOT errors propagate; table/KOT/invoice writes
share the caller's transaction. Table release excludes retained voids and preserves
other active orders in the merge cluster. Native on_cancel/on_trash table cleanup
also uses commit=False. Original matching KOTs use their normal cancel workflow,
with narrow server authorization rather than general KOT cancellation grants.
Cancellation tickets keep comments, route within the profile and print after commit.
Without original live KOTs, no cancellation ticket needs to be generated. With live
KOTs, missing routing/naming or ticket generation fails the transaction visibly.

75 isolated Python checks passed (24 cancellation, 14 extensions, 25 KOT access,
12 opening context) plus the Node cart/cost harness and Python compilation.
These are doubles/source harnesses, not live accounting, KDS or printer acceptance.
Apply on the test site, clear cache and restart shared services; no migration,
frontend build or permission change is required. Test a fresh ordinary tea draft
first, inspect status/docstatus/reason and absence of stock/GL entries, then verify
payment/edit attempts fail and arrangement cancellation is still denied. Table/KOT
cancellation and submitted invoice reversal remain live acceptance items.

### Live draft cancellation verification — 11 November 2026

Backup, patch application, 75 isolated Python tests, Node checks,
cache clearing and shared service restart succeeded.

Cashier cancelled unpaid tea order REG-00020 through the POS interface.
Verified docstatus 0, operational status Cancelled, total QAR 10,
and reason "Draft cancellation test".
Verified zero Stock Ledger Entries and zero GL Entries for the invoice.
Original KOT KOT-URY-00020 became docstatus 2.
Cancellation ticket CNCL-KOT-URY-00003 was submitted with docstatus 1.
Cashier edit/save and payment-access checks both rejected the cancelled
order with the expected cancellation message. Edit attempt was rolled back.

Physical printing, shared-table release and submitted ordinary-invoice
cancellation remain unverified live.
