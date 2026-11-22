# Reusable QZ workstation printing — staging patch

## Scope and status

POS v2 now initializes QZ with callbacks to the EXISTING authenticated endpoints
ury.ury.api.ury_print.qz_certificate and signature_promise.
Private keys remain in site private storage. No backend permissions are changed.
The existing signing endpoint allows its configured QZ_SIGNING_ROLES; it is a
role-authorized signing service, not an invoice-scoped print authorization service.
The existing HTML retrieval and invoice print-status access checks still apply.
Do not expose signing to Guest or broaden roles for the test.

The QZ API exports remain compatible: initPrinting({signKey}) and two-argument
printWithQz still exist for other consumers. POS v2 uses server callbacks and a
third printer-name argument. Legacy consumers using signKey are not migrated.
Secure WebSockets are now required by the shared QZ transport.
No POS Profile, existing CUPS queue or site config is changed by apply.py.

Local checks: 16 mocked QZ transport/orchestration checks and 16 existing
network submission assertions passed. Type checks, full app builds, QZ runtime,
Windows driver output, Arabic, long receipts, cutting and USB hardware remain
unverified. Mock tests do not simulate the actual QZ protocol.

## Apply and validate before activating

Extract the ZIP in /home/frappe, then:

    python3 /home/frappe/URY_QZ_Setup_Patch/apply.py
    cd /home/frappe/frappe-bench/apps/ury
    node tests_offline/test_qz_transport.cjs
    node tests_offline/test_print_submission.cjs
    yarn workspace @ury/core typecheck
    (cd pos && yarn tsc -b)
    (cd frontend && yarn tsc -b)
    yarn ury-posv2-build
    (cd frontend && yarn build)
    git diff --check

Stop on a failed check and report its output. The archive contains only the
changed files, not a complete buildable monorepo. Local TypeScript stripping
and mocks are not a substitute for typechecking the installed project.
After checks pass, clear the test site's cache and hard refresh the POS.
No Python service restart is needed for these frontend changes.

## Prepare Windows separately

Install QZ Tray from the official QZ website and start it on the Windows laptop.
The browser and QZ Tray run on the same workstation. Use localhost as qz_host;
192.168.18.23:9100 is the emulator destination, not the QZ WebSocket host.
Use QZ Tray's installed localhost TLS certificate; do not switch off browser TLS
checks or expose QZ/RAW TCP to the internet.

For development, QZ documents generating a demo certificate/key in Advanced >
Site Manager > + > Create New. Those demo credentials are trusted only on the
installation where generated. Production needs its own signing/trust setup.
Never upload the private key into chat, a public directory, frontend code or Git.

Transfer the generated pair directly to the TEST server securely. Store the
private key as private/qz/private-key.pem with restrictive permissions.
Set qz_private_key in the TEST site's config to qz/private-key.pem.
Set qz_cert in that same site config to the matching certificate PEM CONTENTS,
not its filename. The existing certificate endpoint returns this value verbatim.
Do not overwrite another site's signing identity. Back up config before editing.
Existing server signing roles must authorize the test user.

## Explicit Windows queue selection

On the laptop create a dedicated Windows printer queue through the emulator's
setup wizard. Record its exact Windows queue name. Do not change the laptop's
default printer for this test. The emulator consumes RAW ESC/POS; this patch
sends QZ pixel/HTML jobs through a Windows printer driver. A compatible thermal
driver must convert those jobs to ESC/POS. A Generic/Text Only driver is not
proof that HTML/raster printing works. Driver/emulator compatibility is pending.

In the signed-in POS browser console, configure this workstation only:

    localStorage.setItem('ury.qz.printer.Regnosa Cafe', 'EXACT WINDOWS QUEUE NAME');

Use the actual POS Profile name and Windows queue name. Each customer/profile
gets its own key. The code rejects missing names and approximate printer matches.
Browser storage is an initial deployment mechanism, not a printer-settings UI.
Do not put CUPS Network Printer Settings names in this key.

Only after code validation, credentials, QZ and the Windows queue are ready,
record the current test profile settings and switch the TEST profile to QZ:
qz_print=1 and qz_host=localhost. Refresh the cached profile in the POS browser.
Keep the verified CUPS queue intact for rollback. Do not switch a production
profile based solely on emulator testing. Restore recorded settings to return
to network printing.

## Acceptance tests (pending live)

Use a fresh unpaid draft. Print once, check one receipt and inspect print status.
Test QZ stopped, missing printer, signing denied and print rejection: no success
and no subsequent print-status update. Inspect Windows queue/emulator before
retrying after any error: submission can occur before a later status-update
failure. A resolved QZ request is submission acknowledgement, not paper delivery.
Current QZ UI success text is inherited and still needs acknowledgement wording.
Do not assume CUPS automatic retry behavior applies to QZ or Windows.
Verify short, long and Arabic receipts, paper width, margins and cutting later
with the real Epson/driver. Captain QZ context currently supplies qz_print=0;
Captain QZ support requires separate context work and is outside this patch.

References:
https://qz.io/docs/signing
https://qz.io/api/qz.print.html

## Live development verification — 19 November 2026

Tested QZ Tray 2.3.0 on a Windows development laptop.
Configured matching development certificate and server-side private key
on urytest.erporyxss.com. Server signing verification passed.
Selected Microsoft Print to PDF explicitly for the workstation.

REG-00032 generated a readable PDF with total QAR 10 and DRAFT / UNPAID.
invoice_printed became 1; the invoice remained Draft.
Output used Letter paper; 80mm sizing remains unverified.

With QZ Tray exited, REG-00033 displayed a connection failure and
invoice_printed remained 0. After restarting QZ, one manual retry generated
one PDF and changed invoice_printed to 1. The invoice remained Draft at QAR 10.

All 32 mock assertions, core and POS type checks, and both production
builds passed. Management frontend type checking still reports 39 errors.

The local Epson driver reached the Windows ESC/POS emulator, but its
GS 8 L graphics output rendered incorrectly. Epson/emulator compatibility,
80mm sizing, cutting and physical USB printing remain unverified.

## QZ receipt layout verification — 2026-11-22

- Wrapped receipt HTML in a complete UTF-8 document with a `.print-format`
  container and zero body margins. Empty HTML is rejected.
- Disabled QZ automatic content scaling to preserve receipt dimensions.
- Verified short and 20-item draft receipts using the Epson TM-T88V Receipt5
  Windows driver and ZplEscPrinter emulator.
- Investigated excessive leading whitespace using a captured RAW job:
  the first raster block contains heading pixels on its first row.
  The preceding feed command requests 74 motion units, approximately 9 mm
  at 203 dpi. The large displayed blank area points to emulator rendering.
- QZ transport checks, print submission checks, core and POS TypeScript
  checks, and the POS production build passed.
- Physical printer spacing and cutting remain unverified.
