# PKI credentials in the Credential Manager - plan

Branch: `feature/pki-credentials` (based on `main`).

## Goal

Let a credential set authenticate with an SSH key pair instead of a password. Phase 1 is an SSH private key with an
optional passphrase. The design must make later credential types (OpenSSH certificate, TLS client certificate) an
additive change.

## Current state

- Credential sets live in `cred_sets.json` as `{id, name, username_enc, password_enc}`. Values are encrypted with
  `_encrypt` / `_decrypt` (key in `.rosm_key`).
- All authentication is a `(username, password)` tuple:
  - `_resolve_cred_id`, `_get_creds_for_site`, `_get_device_creds` return a tuple.
  - `_ssh_connect(ip)` and `_ssh_connect_creds(ip, user, pw)` call `paramiko.SSHClient.connect(..., password=...)` with
    `look_for_keys=False, allow_agent=False`.
  - Callers pass `ssh_user` / `ssh_pass` through worker threads (backup, upload/import, RouterOS check, install,
    download, NPK, discovery, custom columns).
- Legacy per-device credentials (`ssh_user`, `ssh_pass_enc`) exist as a fallback and stay password-only.
- Credentials page (`render_credentials_page`) and several pickers only handle name, username and password.

## Design

1. **Typed credential record.** Add `type` to each set (`"password"` by default, so existing files keep working with no
   migration). New types add their own encrypted fields:
   - `password`: `username_enc`, `password_enc` (unchanged).
   - `ssh_key`: `username_enc`, `private_key_enc`, `passphrase_enc` (optional), plus non-secret `key_type` and
     `fingerprint` for display.
   - Future `ssh_cert`: adds `certificate_enc`. Future `tls_client`: `cert_enc`, `key_enc`.
2. **One resolver returning a credential object.** `_resolve_credential(cred_id)` returns
   `{"type", "username", "password", "private_key", "passphrase", ...}`. `_resolve_cred_id` stays as a thin wrapper
   returning `(user, password)`, so password-only call sites keep compiling during the migration.
3. **One place that builds connections.** A single `_ssh_connect_cred(ip, cred)` maps the credential type to
   `paramiko` arguments (`password=` or `pkey=`). `_ssh_connect` and `_ssh_connect_creds` delegate to it.
   Adding a type later means adding one branch here.
4. **Pass the credential object, not two strings.** Worker functions that take `ssh_user, ssh_pass` move to a single
   `cred` argument (about 12 call sites, listed in the checklist below). The tuple wrapper is removed once none remain.
5. **Key loading.** Parse with `paramiko.PKey.from_private_key` trying `Ed25519Key`, `ECDSAKey`, `RSAKey`
   (`DSSKey` is not supported). Reject invalid or passphrase-protected keys without a passphrase at save time, so errors
   show in the UI and not as a failed backup.
6. **Security.**
   - Private keys and passphrases are encrypted like passwords and never returned to the browser. The edit form shows
     only type, key type and fingerprint; a blank secret field on edit means "keep existing".
   - Never write keys to disk in plain text and never log them. Keys are loaded in memory via `io.StringIO`.
   - Limit key size (e.g. 16 KiB) on upload; reuse the existing POST size limits.
   - Fingerprints (SHA256) shown to the user for verification.
7. **RouterOS side.** RouterOS needs the matching public key imported for the user (`/user ssh-keys import`). Show the
   derived public key in the UI with a copy button and a short instruction. Optionally provide a generate-key-pair
   action (Ed25519) that shows the public key once and stores the private key.
8. **Compatibility.** Existing `cred_sets.json` files, sites referencing `credential_id`, and devices keep working. A
   set without `type` is `password`.

## Phases

1. Refactor: introduce `_resolve_credential`, `_ssh_connect_cred`, keep tuple wrapper; no behaviour change. Tests.
2. Add the `ssh_key` type to the data layer (`cred_set_add` / `cred_set_update`), key validation and fingerprint.
3. Move callers from `(user, pass)` to the credential object; remove the wrapper.
4. Credentials page: type selector, key paste/upload, passphrase, public key and fingerprint display, passphrase-less
   key warning. Pickers show the credential type.
5. Future (not this branch): generate a key pair in the app, show the public key and RouterOS import command.

## Progress

- Phase 1 done (`c2c740e`): credential objects, `_resolve_credential`, `_ssh_connect_cred`; tuple helpers kept as wrappers.
- Phase 2 done: `ssh_key` sets in the data layer (`cred_set_add` / `cred_set_update`), key parsing (`_load_private_key`: Ed25519, ECDSA, RSA, with passphrase), `_key_fingerprint`, `_key_public_line`, encrypted storage, `_ssh_auth_kwargs` key branch, and `/api/creds/add|update|reveal` wiring. Reveal returns only metadata for key sets. `_cred_set_public` is the only shape sent to the browser. Fingerprint and public key line verified against `ssh-keygen`.
- Phase 3 done: every call site (scan, add devices, backup, RouterOS jobs, SFTP push, bulk and upload import) passes credential objects instead of `(user, pass)` tuples. Key sets chosen in "add devices" are linked through `credential_id`. The tuple wrappers were removed, and `_cred_usable` replaces the old "has a password" checks.
- Key tests need `paramiko` and `cryptography` (run with the project venv); they skip otherwise.
6. Documentation, English/Italian strings (use `T()` / `lang_en`), manual test against a RouterOS device.

## Call sites to migrate (line numbers on `main`, approximate)

`_get_device_creds` (1005), `_get_creds_for_site` (2284), `_ssh_connect` (2008), `_ssh_connect_creds` (2018),
`backup_router` / `backup_all` (ssh_user, ssh_pass), `_upload_import_worker` (~2684), device add (~5627, 5645),
override creds (~5889), credential reveal (~5960), RouterOS check/install/download/NPK (~6101, 6184, 6247, 6313, 6361).

## Testing

- Unit: record migration (missing `type` -> password), key parsing for ed25519/ecdsa/rsa, bad key, encrypted key with
  and without passphrase, fingerprint, `_ssh_connect_cred` kwargs per type (paramiko mocked).
- Regression: password credentials produce the same `connect()` arguments as before.
- Manual: key auth against a RouterOS device; backup, upload, refresh.

## Decisions

- **Reveal never shows a private key.** The reveal action returns no key material for `ssh_key` sets. If a display is ever needed, show the fingerprint only.
- **Key-based sets can be device specific.** A key set is a normal named set, so it can be assigned to a single device (`credential_id`) as well as to a site. The legacy per-device `ssh_user` / `ssh_pass_enc` fields stay password-only.
- **Phase 1 is paste/upload only.** No key-pair generation in the app, so phase 5 is dropped from this branch and moved to future work.
