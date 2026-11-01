# CGI removal: exposure review and migration plan

## Executive summary

The original branch directly imported Python's deprecated `cgi` module in
`dashboard.py` to parse POST forms. That caused application startup to fail on
Python 3.13+, where `cgi` was removed. The migration now replaces that parser
with the standard-library `email` MIME parser for multipart bodies and
`urllib.parse` for URL-encoded bodies. It adds a configurable 10 MiB body/file
limit and writes accepted uploads in chunks through a temporary file before
replacing the destination.

The implementation keeps the existing `http.server` architecture and adds no
runtime package dependency. The multipart body is parsed in memory, as
explicitly chosen for this migration; the size limit bounds each request, but
does not cap aggregate memory usage across concurrent requests.

## Current exposure

### Direct use before migration

- [`dashboard.py`](./dashboard.py) imported `cgi` at top level, making Python
  3.13+ a startup compatibility issue even when a user never submitted a form
  or uploaded a file.
- The authenticated POST handler constructed one `cgi.FieldStorage` object.
  Its parsed fields were used by RouterOS update operations and four upload
  flows.
- The affected form routes are `/api/ros-check-start`, `/api/ros-install`,
  `/api/ros-download`, `/upload_npk`, `/upload_import`, `/upload_ssh`, and
  `/upload_bulk`. The upload routes carry files; the RouterOS operation routes
  carry ordinary form fields. Frontend callers use `FormData` for these
  requests.
- JSON API paths were handled and returned before `FieldStorage` was reached.
  Other URL-encoded POST handling already used `urllib.parse.parse_qs`; those
  paths were not direct `cgi` consumers.

### Operational impact

- Python 3.11 and 3.12 deprecated but retained `cgi`; Python 3.13+ removed it.
- The direct import and `FieldStorage` call have been removed from the source.
  Python 3.14.7 syntax compilation and focused parser tests pass, but a full
  application startup was not verified because this workspace's Python
  environment does not have the app's existing `paramiko` dependency.
- This checkout has no dependency manifest or installer/build scripts, even
  though the code overview mentions `requirements.txt` and installer scripts.
  The runtime versions actually shipped to users therefore cannot be confirmed
  from the present checkout. The `Python 3.9 compat` comment in `dashboard.py`
  is a compatibility hint, not an authoritative support declaration.
- `cgi` is a Python standard-library module, not an external package declared
  in this checkout. Its removal cannot be addressed by removing a third-party
  requirement alone.

### Upload handling and remaining risk

`MAX_UPLOAD_SIZE_BYTES` is set to `10 * 1024 * 1024` in `dashboard.py` and is
used to reject oversized form bodies before reading them and oversized file
parts before saving. `email` builds a MIME tree in memory, so memory per
request is bounded by the request cap but is higher than 10 MiB due to parsed
objects and payload copies. Concurrent requests can multiply that usage.
Accepted file bytes are copied in 64 KiB chunks to a temporary file and moved
into place atomically; failed copies remove the temporary file.

The handler does apply authentication and per-route permission checks before
the shared parser is reached. The migration leaves that ordering unchanged.

## Recommendation

The selected implementation uses `urllib.parse.parse_qs` for
`application/x-www-form-urlencoded` and `email.parser.BytesParser` with the
standard MIME policy for `multipart/form-data`. This avoids a new runtime
dependency because the checkout's dependency and installer metadata is
missing. Parsing is bounded by `MAX_UPLOAD_SIZE_BYTES`; it deliberately does
not implement multipart boundary parsing by hand. Repeated names keep
`FieldStorage`-like scalar-versus-list behavior, and uploaded files expose a
filename and file-like object to the existing route handlers.

The standard-library parser choice trades streaming request parsing for ease
of deployment and bounded per-request input. If aggregate memory pressure
proves problematic, revisit a streaming parser together with restored
dependency and installer metadata. Do not switch to `legacy-cgi`: Python's
documentation identifies it as an unmaintained copy of `cgi`.

## Progress against plan

1. **Release targets and packaging — investigated, unresolved.** The
   authoritative Python range, dependency manifest, and macOS/Windows build
   files are absent from this checkout. Whether installers bundle Python or
   depend on a system interpreter remains unconfirmed.
2. **Parser contract — implemented.** Support URL-encoded and multipart forms,
   retain repeated values as lists, reject malformed or unsupported bodies,
   and enforce the approved 10 MiB request/file limit via
   `MAX_UPLOAD_SIZE_BYTES`.
3. **Parser migration — implemented.** A shared parser normalizes form and
   file values for the existing routes. The `cgi` import and `FieldStorage`
   access have been removed.
4. **Validation — partially complete.** Ten standard-library `unittest`
   cases cover parser fields/files, duplicate values, malformed bodies,
   content-length validation, oversize rejection, source import removal, and
   temporary-file cleanup. Full route-level tests and application startup on
   Python 3.13+ and the oldest supported runtime remain outstanding; the local
   Python 3.14.7 environment lacks the existing `paramiko` dependency.
5. **Release integration — pending.** Restore authoritative dependency,
   installer, CI, and user-facing Python prerequisite files before claiming
   packaged macOS/Windows compatibility.

## Acceptance criteria

- No application source imports or references `cgi` or `FieldStorage`.
- Application startup and the applicable CI/build matrix succeed on Python
  3.13+ and all retained supported Python versions.
- The seven affected routes preserve their existing field names, response
  shapes, authorization checks, and successful file-transfer behavior.
- Body and file size limits are enforced before parsing; saved file content is
  copied in chunks, and temporary files are cleaned up reliably.
- Runtime and packaging validation must be completed when the omitted release
  metadata becomes available.

## References

- [Python `cgi` module documentation](https://docs.python.org/3/library/cgi.html):
  states that `cgi` was deprecated in Python 3.11 and removed in Python 3.13;
  it describes `legacy-cgi` as a copy no longer maintained or supported by
  Python core developers.
- [`dashboard.py`](./dashboard.py): direct import, POST dispatch, shared
  `FieldStorage` call, and upload helper.
