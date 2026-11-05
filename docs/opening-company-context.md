# POS opening company context fix

Observed on urytest.erporyxss.com for regnosa.cashier@example.com:
the explicit-user default lookup returned Regnosa, but the session-level lookup
returned None. The opening API then used the site's Oryx Security Systems company
and failed Company read permission before returning the opening context. The
screen displayed a generic session-opening permission message despite all four
POS Opening Entry permissions being granted.

The opening API now resolves company from an authorized branch/selected profile
first. It validates the profile through the existing access helper and the
company's assigned-profile list. Explicit-user defaults are considered only if
there is no active profile. Defaults that the user cannot access are ignored.
Without a usable default, permission-filtered and independently authorized
profiles may supply a company only when exactly one company is available.
No site-wide company fallback, permission bypass or role grant is introduced.

Actual branch/profile PermissionErrors still propagate. Other exceptions are
not hidden: only a missing branch/configuration ValidationError allows fallback.
The optional pos_profile argument already sent by the React selector is now
accepted and validated by the API.

Validation: 12 targeted offline/double tests include the actual opening API body;
14 existing extension tests and 25 KOT tests also pass. Python compilation and
patch whitespace checks pass. Live Frappe/browser confirmation remains pending.

Apply this fix on top of the uncommitted/applied Stage 3 changes without resetting
or replacing those changes. Run tests, clear the test-site cache and restart shared
bench services. No build/migration is needed. Keep arrangement settings disabled.
Record the live result in Flora's operations guide before pushing the combined
Stage 3 and fix changes in the two feature branches.
