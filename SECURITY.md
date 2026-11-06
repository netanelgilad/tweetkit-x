# Security review — 2026-11-06

This is a scoped source review and regression-test pass, not a security certification. No live posting, deleting, following, liking, or messaging was performed during installation.

## Findings fixed

- **Session exposure through MCP:** upstream auth tools asked for session headers through model-visible tool arguments. Removed cookie setup/import tools; the installed integration obtains only X cookies internally from Chrome and sends them to a local Python child on stdin.
- **Arbitrary local-file uploads:** upstream MCP accepted media paths. The installed catalog accepts bounded base64 image bytes and checks the claimed image's signature; no arbitrary local paths or URL fetches.
- **Redirect and destination leakage:** all client HTTP requests use a restricted HTTPS session. Authenticated destinations are exactly `x.com`, `api.x.com`, and `upload.x.com`; public bootstrap assets may additionally use `abs.twimg.com`. Redirects, ambient proxy/netrc authentication, and automatic retries are disabled. Bootstrap no longer submits HTML-selected migration forms.
- **Unbounded and misleading responses:** response size, child output, input sizes, execution duration and media polling are bounded. HTTP errors and GraphQL error responses fail explicitly instead of returning an empty successful result. Upstream error bodies and network exception details are not returned.
- **Cookie file race/symlinks:** cookie saving uses a private temporary file and atomic replacement; existing symlinks cannot overwrite their targets. Implicit current-directory cookie loading was removed. Keychain writes that put secrets into process arguments are disabled.
- **Import origin confusion:** HAR imports parse hostname rather than substring matching; JSON exports filter declared cookie domains. ZIP cookie entry size is bounded.
- **Unbounded agent input:** an explicit operation catalog is validated in both Node and Python. It rejects unknown fields, arbitrary methods, cookie inputs, paths, malformed identifiers, oversized pages and oversized threads. Regex search and bulk deletion are not exposed.
- **Account switching:** private user-ID pinning refuses a different logged-in account and refuses writes before identity setup.
- **Dependency drift:** direct transaction dependency replaces the compatibility shim; runtime dependencies are pinned with hashes in `requirements.lock`. MCP is constrained to its compatible v1 API. The original unbounded MCP dependency resolved to an incompatible v2 release during testing.

## Verification

- 20 Python security/request tests pass.
- 7 new companion tests pass, including authentication, Origin rejection, cross-account rejection, strict inputs and cookie filtering.
- Companion suite: 39 tests and 54 smoke checks pass.
- Executor app strict TypeScript check and deployment pass.
- Dependency scan with pip-audit 2.10.1: no known vulnerabilities found in installed dependencies. The local fork itself is source-reviewed, not covered by PyPI vulnerability matching.
- Chrome and both existing WhatsApp connection status reads work after activation.
- Authenticated X reads are **not yet verified**: an X tab must be open and signed in in the connected Chrome profile.

## Trust boundaries and remaining limits

- The owner, OS account, Chrome profile/extension, companion registry, Executor account store and installed dependencies are trusted. This does not sandbox a compromised dependency or protect against a compromised Mac.
- The bridge bearer authorizes module operations. Write approval is enforced by the Executor tool layer, not cryptographically verified by the companion. Do not grant the bridge account to untrusted apps or users.
- Cookies are memory-only in this integration, but Chrome itself stores its session normally. The standalone trusted-local CLI/library can still load explicitly configured local credentials and upload caller-selected files; do not expose those interfaces directly to untrusted callers.
- Image magic checks are not a full media parser or malware scan. Small-image uploads only (200 KB); video support is not exposed.
- No live writes have been tested. Partial threads and interrupted writes can have uncertain outcomes; inspect X before retrying. There is no claim of exactly-once delivery or comprehensive request parity with today's X web client.
- X may change endpoints, restrict account features or challenge the session. Stop on a block/challenge; sign in normally. The fork does not bypass those challenges.
- DMs, list management and Spaces are unsupported. Unofficial session access remains subject to X's service rules and account restrictions.

For reporting a vulnerability, do not include session cookies, HAR files or personal account data in a public issue.
