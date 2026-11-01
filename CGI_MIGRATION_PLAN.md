# CGI removal: exposure review and migration plan

## Executive summary

The application has one direct dependency on Python's deprecated `cgi` module:
`dashboard.py` imports it at module scope and later uses `cgi.FieldStorage` to
parse POST form bodies. The import is present in Python 3.12 and earlier, but
the module was deprecated in Python 3.11 and removed from the standard library
in Python 3.13. On Python 3.13 or newer, importing `dashboard.py` therefore
fails before the server starts.

The dependency is confined to request-body parsing; the application does not
otherwise use CGI execution or CGI environment behavior. The migration can
preserve the existing `http.server` architecture and avoid a web-framework
rewrite.

## Current exposure

### Direct use

- [`dashboard.py`](./dashboard.py#L60) imports `cgi` at top level. This makes
  Python 3.13+ a startup compatibility issue even when a user never submits a
  form or uploads a file.
- [`dashboard.py`](./dashboard.py#L6084) constructs one `cgi.FieldStorage`
  object in the authenticated POST handler. Its parsed fields are used by
  RouterOS update operations and four upload flows.
- The affected form routes are `/api/ros-check-start`, `/api/ros-install`,
  `/api/ros-download`, `/upload_npk`, `/upload_import`, `/upload_ssh`, and
  `/upload_bulk`. The upload routes carry files; the RouterOS operation routes
  carry ordinary form fields. Frontend callers use `FormData` for these
  requests.
- JSON API paths are handled and returned before `FieldStorage` is reached
  ([`dashboard.py`](./dashboard.py#L5599)). Other URL-encoded POST handling
  already uses `urllib.parse.parse_qs`; those paths are not direct `cgi`
  consumers.

### Operational impact

- Python 3.11 and 3.12 emit a deprecation warning for this import/use, but
  retain the module.
- Python 3.13+ no longer includes `cgi`. Without a replacement installed,
  application startup fails with `ModuleNotFoundError`.
- This checkout has no dependency manifest or installer/build scripts, even
  though the code overview mentions `requirements.txt` and installer scripts.
  The runtime versions actually shipped to users therefore cannot be confirmed
  from the present checkout. Treat their Python version range as an open
  release-engineering question, not as evidence that users are currently
  protected from the failure.
- `cgi` is a Python standard-library module, not an external package declared
  in this checkout. Its removal cannot be addressed by removing a third-party
  requirement alone.

### Related upload concerns to address with the migration

The POST handler reads `Content-Length` but currently applies no visible
request-body size limit before parsing
([`dashboard.py`](./dashboard.py#L5447)). `_save_upload` then reads the entire
uploaded file into memory before writing it to disk
([`dashboard.py`](./dashboard.py#L2636)). Large or deliberately oversized
uploads can therefore consume substantial memory. The parser replacement
should not preserve this weakness by default; add an explicit, product-approved
body/file size limit and stream uploaded bytes to a temporary file before
moving them to the upload destination.

The handler does apply authentication and per-route permission checks before
the shared parser is reached ([`dashboard.py`](./dashboard.py#L5025)). Those
checks must remain in place and be covered by regression tests.

## Recommendation

Replace `cgi.FieldStorage` with a small internal form-parsing boundary that
normalizes fields and uploaded files for the existing route handlers. Use
`urllib.parse.parse_qs` for `application/x-www-form-urlencoded`, which is
already used elsewhere in the server. For `multipart/form-data`, prefer a
maintained, purpose-built multipart parser (for example, `python-multipart`)
with streaming/file callbacks if compatible with the project's packaging
targets. Add and pin that dependency in the actual dependency manifest and
ensure both installers bundle it.

Keep the parser behind an application-owned helper/API so route code does not
depend on parser-library-specific objects. The normalized result should make
repeated fields explicit and provide uploaded file metadata plus a file-like
stream or temporary-file path. Do not select `legacy-cgi` as the long-term
solution: Python's documentation identifies it as an unmaintained copy of
`cgi`, so it postpones rather than completes the migration.

Before committing to the parser and dependency, restore or locate the
authoritative requirements/build configuration and confirm support for every
Python version and installer target. If adding a dependency is incompatible
with the distribution model, evaluate a standard-library MIME parser
implementation separately and require the same conformance and resource-limit
tests; do not introduce an ad hoc boundary-splitting parser.

## Staged implementation plan

1. **Confirm release targets and packaging.** Find the authoritative supported
   Python range, dependency lock/manifest, and macOS/Windows packaging files.
   Verify whether built installers bundle Python and dependencies or rely on
   a system interpreter. Add Python 3.13+ to CI/build validation while keeping
   all currently supported versions.
2. **Specify the parser contract.** Define supported content types, required
   fields, repeated-field behavior, filename handling, malformed-request
   responses, and approved maximum request and file sizes. Preserve existing
   route-level authentication and permissions.
3. **Implement and migrate centrally.** Add a shared parser helper for
   URL-encoded and multipart forms. Stream file parts to bounded temporary
   storage; validate the declared and consumed body size; clean up temporary
   files on parser errors and downstream failures. Update the seven listed
   routes and `_save_upload` to consume the normalized representation. Remove
   the `cgi` import and all `FieldStorage`-specific access.
4. **Prove behavior before release.** Add tests for each route's fields and
   file behavior, including binary file contents, empty/missing files,
   repeated fields, filenames with path components, malformed boundaries,
   unsupported content types, absent/invalid/oversized content lengths, and
   cleanup on failure. Assert that unauthorized users remain denied. Run the
   focused suite and start/import the app on Python 3.13+ and the oldest
   supported interpreter.
5. **Ship consistently.** Update dependency metadata, installer bundling,
   CI, and user-facing Python prerequisites together. Confirm the packaged
   macOS and Windows applications execute the same upload/update smoke tests.

## Acceptance criteria

- No application source imports or references `cgi` or `FieldStorage`.
- Application startup and the applicable CI/build matrix succeed on Python
  3.13+ and all retained supported Python versions.
- The seven affected routes preserve their existing field names, response
  shapes, authorization checks, and successful file-transfer behavior.
- Body and file size limits are enforced before unbounded memory use; uploaded
  content is streamed and temporary files are cleaned up reliably.
- Dependency installation and both packaged distributions include the chosen
  parser implementation where required.

## References

- [Python `cgi` module documentation](https://docs.python.org/3/library/cgi.html):
  states that `cgi` was deprecated in Python 3.11 and removed in Python 3.13;
  it describes `legacy-cgi` as a copy no longer maintained or supported by
  Python core developers.
- [`dashboard.py`](./dashboard.py): direct import, POST dispatch, shared
  `FieldStorage` call, and upload helper.
