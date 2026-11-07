# Marshal onboarding and administrator review

Migration `0020` requires every marshal, including existing accounts, to complete
onboarding. New duty/dispatch/acceptance requires `APPROVED` status. No account is
automatically approved and old on-duty flags are cleared by the migration.

The native marshal app collects legal name, adult birth date, mobile number,
residential address, a passport/driving licence/voter ID number and clear ID
image, a clear portrait, and an emergency contact name, relationship and number.
A spouse is one option; marriage is not required. The contact must have a
different number and the marshal must confirm the contact was informed.

Aadhaar is deliberately excluded from this manual image-review flow. Do not
accept Aadhaar under another document type. Integrate an appropriate consensual
UIDAI verification flow before adding Aadhaar support. Administrator approval
is an operational review, not government e-KYC, phone OTP verification, biometric
liveness or a criminal/background check.

## Private storage

Configure `MARSHAL_IDENTITY_KEY` as a dedicated Fernet key and
`MARSHAL_IDENTITY_ROOT` as a private absolute folder outside publicly served
media. Generate a key with `Fernet.generate_key()`; never reuse `JWT_SECRET`.
Back up the key securely, separately from database/documents. Losing or replacing
the key makes existing data unreadable; key rotation needs an explicit re-encryption
procedure. Keep both settings backend-only. Docker deployments must mount the
private directory and pass both settings before onboarding is enabled there.

The canonical Compose deployment passes `MARSHAL_IDENTITY_KEY` from its private
`backend/deployment/.env` and fixes `MARSHAL_IDENTITY_ROOT` at
`/var/lib/securepulse/marshal-identities/documents`. The separate
`marshal_identities` named volume persists that folder across backend container
replacement. The application creates the `documents` child with private
permissions. Identity storage is never mounted into the dashboard or a media
server. Back up this volume together with the onboarding database records and
the separately protected encryption key. Preserve the existing Compose project
name and volumes; `docker compose down -v` deletes the documents.

Identity submissions require HTTPS in both the native form and backend. The
current HTTP LAN address can show the form but cannot submit personal documents.
Serve the existing backend through an authenticated HTTPS deployment/reverse
proxy and set the mobile server origin to that HTTPS URL. Forwarded schemes
must come only from a trusted proxy. Never enable insecure test mode with real
personnel data. `MARSHAL_IDENTITY_INSECURE_TEST_MODE=true` is a backend-only
development exception for isolated synthetic-data tests; production ignores it.

Personal details are encrypted before writing the database. Images are bounded,
decoded, re-encoded without EXIF and encrypted on disk under random filenames.
Files use mode 0600 and newly created directories use 0700. A database reader
sees only document type, ID last four characters, review status and timestamps.
Owner/dispatcher APIs never expose identity documents or emergency contacts.
Authenticated marshals can read only their own documents; responses disable
HTTP caching. No personal input or document contents are added to audit events.

## Review locally

From `backend/`, with the trusted administrator's environment activated:

```sh
python -m app.review_marshal
# Choose a NEW private directory; do not export into public media or the repo.
python -m app.review_marshal --inspect MARSHAL_PROFILE_ID --reviewer YOUR_ADMIN_NAME --output-dir /private/review/unique-review-folder
```

The second command explicitly decrypts a private review copy and logs the export.
Inspect the ID using the issuer's appropriate verification process, compare the
portrait and name, confirm adult age and address, contact the marshal and check
the nominated emergency contact. Confirm the consent statements. Reject blurry,
mismatched, expired or unsupported documents. Do not approve a blank/test profile.

```sh
python -m app.review_marshal --approve MARSHAL_PROFILE_ID --reviewer YOUR_ADMIN_NAME --reason "Identity and contact checks completed" --confirm-checks
# Or request corrections; the reason is visible to the marshal:
python -m app.review_marshal --reject MARSHAL_PROFILE_ID --reviewer YOUR_ADMIN_NAME --reason "Please upload a readable ID front"
```

Reviewer access is a trusted local administrative capability, not a new public
API role or permission granted to ordinary property owners. Securely remove
review exports after the review according to the organization's retention policy;
the app cannot delete exports an administrator copied elsewhere.

The marshal sees pending/rejected/approved state and can resubmit after rejection.
Approved or pending submissions cannot be overwritten through the app. For
corrections, withdraw then resubmit; this disables duty until reviewed again.
Withdrawal deletes encrypted details and documents from active storage and
retains non-PII audit events. Active assignments must first be closed by dispatch.
Backups and exported review copies require the administrator's retention/deletion
process. Establish the privacy notice, retention period and authorized review
staff before collecting real personnel documents in a production deployment.

## Verification

```sh
python -m pytest tests/test_marshal_onboarding.py -q
# mobile/marshal-app
npm run typecheck
npx expo-doctor@latest
```
