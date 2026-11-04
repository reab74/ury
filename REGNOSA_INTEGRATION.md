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
