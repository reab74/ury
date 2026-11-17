# CUPS submission failure propagation

A live test rejected new jobs on Regnosa_Virtual_Cashier using cupsreject.
The normal POS print action displayed success despite no receipt arriving.
Queue acceptance was restored and no pending job remained.

## Change

network_printing now raises on missing CUPS, connection failure, printFile
rejection or an invalid job ID. PDF errors also propagate. It marks print status
and invokes the existing table-release behavior only after a positive CUPS job
ID. Temporary PDFs are private, securely created and cleaned on failure/success.
The existing successful response remains the string Success for compatibility.
CUPS connection uses explicit host/port rather than process-global setters.

Both frontend API wrappers require that exact successful response. Legacy failure
strings, empty responses or malformed payloads throw and stop printOrder before
its updatePrintStatus call. No new success notification is added. Existing UI
success text means queue submission, not physical delivery.

select_network_printer accepts the print_format argument already sent by the
frontend, checks invoice/profile identity and raises if no bill printers exist.
Existing Take Away profile routing and Dine In room routing are retained.
Printing permissions remain checked; no permissions are granted by this patch.

## Validation

10 isolated Python tests pass: rejection, connection/PDF errors, invalid job IDs,
spool cleanup, positive acceptance, table-release timing, missing routing,
profile mismatch and routed rejection. 16 Node assertions exercise actual API
function bodies and printOrder network branches with injected dependencies.
The Node harness narrowly erases TypeScript signatures/casts; it is not a full
frontend build. Python compilation passed. Full build and live acceptance are
required on the VPS. Re-run relevant existing offline suites there as well.

## Deployment

Backup the test site with files. Apply using the included guarded apply.py on
feature/regnosa-unified-pos. It requires exact uploaded source hashes or already
patched bytes, preserves existing different tests/docs, and backs up overwritten
files under /home/frappe outside the repository.

    cd /home/frappe/frappe-bench/apps/ury
    /home/frappe/frappe-bench/env/bin/python -m unittest discover -s tests_offline -p 'test_print_submission.py' -v
    node tests_offline/test_print_submission.cjs
    git diff --check
    yarn ury-posv2-build

Build only the POS workspace. No package install, migration or site settings
change is required. Then clear the test-site cache and restart Bench services.
The code and service restart affect every site sharing this Bench. A hard refresh
loads new frontend assets. Do not commit generated build artifacts accidentally.

## Live acceptance

First verify queue empty using lpstat -o Regnosa_Virtual_Cashier. Use a fresh,
unpaid Take Away draft, capture its invoice_printed flag, total and docstatus.
Do not reset a previously printed order's flags to manufacture a fresh test.
Reject only this dedicated queue, click Print once, capture UI error and verify
no new print flag or table change. Restore cupsaccept immediately even if the
UI fails. Queue should have no new job. Then click Print once with acceptance
restored and verify one emulator receipt and the expected print flag.
Keep the draft unpaid. Check a routed/room printer separately before claiming
Dine In acceptance. No automatic retry is added.

## Limits / recovery

Submission acceptance is not delivery confirmation. Offline-after-acceptance,
CUPS filter failures and backend retries may occur after a positive job ID.
This patch does not poll delivery state or prevent duplicated manual submissions.
A multi-printer route can partially submit before a later printer rejects;
previously accepted jobs cannot be rolled back with the database. Inspect queues
before retrying such a route. Existing table-release-on-submission behavior and
merged-bill handling are not redesigned here. Physical printing is unverified.

To roll back, restore only files listed in the printed backup directory, remove
only newly added patch test/docs files if desired, rebuild the POS and restart
services. Restore dedicated queue acceptance if still rejected. Do not reset
unrelated repository changes or delete backups.

## Live verification — 16 November 2026

Tested unpaid draft REG-00028, total QAR 10.
With the dedicated CUPS queue rejecting requests, URY displayed Print failed.
invoice_printed remained 0; the invoice remained Draft; no job was queued.

After restoring queue acceptance, one retry delivered the receipt to the
emulator and invoice_printed became 1. The invoice remained Draft.
CUPS job 7 completed; the queue returned to idle with no pending jobs.

All 10 backend tests, 16 frontend assertions and the production build passed.
CUPS acceptance confirms submission, not physical printer delivery.
Offline-after-acceptance and physical hardware remain unverified.

## Live paused-queue recovery — 16 November 2026

Tested unpaid draft REG-00029, total QAR 10.
Paused only Regnosa_Virtual_Cashier while leaving job acceptance enabled.
One URY Print click submitted CUPS job 8; no receipt arrived while paused.
After cupsenable, exactly one receipt reached the emulator automatically,
without another Print click. The queue returned to idle with no pending jobs.

The UI displayed Printed Successfully before delivery.
Network-print success wording is being corrected to Submitted to print queue.
This test verifies paused-queue recovery, not a network outage.

## Network-print wording verification — 17 November 2026

Orders screen now displays Submitted to print queue after network submission.
Added English, Arabic and French translations.
Updated Orders, Table and Captain bill-print success messages.
Corrected the Orders profile reference to posStore.posProfile.
Frontend build passed. Orders wording verified live.
Table and Captain wording remain unverified live.

## Table and Captain verification — 18 November 2026

Verified unpaid dine-in order REG-00030 from both the Tables screen
and Captain Print Bill at /pos/order, using the cashier session.
Each action displayed Submitted to print queue and delivered one receipt
to the emulator. The order remained unpaid.

Orders, Tables and Captain network-print wording are now verified live.
Captain-only user access remains unverified; the route guard documents
an existing outer billing-access restriction.

## Live network-outage recovery — 18 November 2026

Tested unpaid draft REG-00031 using the dedicated emulator queue.
Temporarily rejected outbound TCP to 31.76.75.231:10141 only,
with a scheduled automatic rollback.
One Print click submitted CUPS job 15. During the block, CUPS reported
the printer unavailable and retained the job.
Removed the firewall rule and stopped the fallback timer.
Exactly one receipt arrived automatically without another Print click
or manual queue resume. The order remained unpaid.
The queue returned to idle with no pending jobs.

This verifies recovery from connection rejection before delivery.
Mid-receipt interruption and physical hardware remain unverified.
