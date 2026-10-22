# Security and support

Report a security issue privately to **wicalgambles@gmail.com**. Include the
version, a minimal synthetic reproducer and the expected behavior. Do not send
credentials, private model outputs or personal data. Public bug reports can use
the repository's Issues page after sensitive information is removed.

Security and correctness fixes target the latest 1.x release. Reports from older
versions are welcome; reproduce with the latest version when possible.

The browser app binds to `127.0.0.1`, uses a fresh session token, rejects foreign
origins, and exposes fixed routes without a filesystem API. It limits upload size,
rows, JSON nesting and active HTTP workers. It is intended for a local single-user
session. Keep the launch URL private and stop the server after use.

Reports and replay JSON can include the complete uploaded data. Review them
before sharing. Registered Python extensions are trusted local code. NPZ inputs
are read with pickle disabled and explicit archive, shape and label checks.
Conversion writes individual files with atomic replacement; a multi-file report
is not a transactional database. A failed run should be retried into a fresh
output directory. Conversion manifests identify bytes and declared settings;
they do not authenticate the author or establish scientific validity.
