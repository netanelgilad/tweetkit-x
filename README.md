# tweetkit-x — reviewed personal Executor fork

Fork of [nsozturk/tweetkit-x](https://github.com/nsozturk/tweetkit-x), retaining the MIT license. Uses your own X web session; no paid API key. This fork adds a restricted Executor integration and security regression tests. It is **not a guarantee of security or continuing compatibility with X**.

## Executor integration

`integrations/mac-companion/` contains the reviewed companion module and Executor app source. It exposes 37 operations: 15 reads/status and 22 writes. All deployed write tools require Executor approval. Capabilities include profiles, timelines, search, conversations, bookmarks, notifications, followers/following, posts/replies/threads/quotes, small image posts, scheduled posts, likes/reposts, follow/block/mute, deletion and pinning.

DMs, list management and Spaces are not implemented. Images are supplied as base64 bytes (200 KB maximum); arbitrary host paths and URLs are not accepted. Account entitlements and X's current endpoint availability still apply. Writes have not been exercised against a live account during installation.

The companion reads only `auth_token`, `ct0` and `twid` for `https://x.com/` from the already signed-in Chrome profile. Values pass directly to a bounded one-shot Python process over stdin. They never enter Executor tool arguments, source, logs, environment variables or command arguments, and are not saved by this integration. First run `status` to pin the X user ID. Subsequent account switches are refused. Chrome must be running with an X tab open and the companion extension connected.

## Local setup and verification

```sh
uv venv .venv
uv pip install --python .venv/bin/python --require-hashes -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
```

The pinned dependencies suffice for running `python -m tweetkit_x.runner` from the repository. Do not put session values in chat. The runner's internal stdin protocol is for the local companion, not a public API.

The standalone `tweetkit-mcp` server is now **read-only stdio**, exposing `capabilities` and `read`. It does not offer cookie setup, file import, or write tools. For standalone use, configure authentication locally. The Python library/CLI remain trusted-local interfaces; do not expose them directly as an unauthenticated service.

See [SECURITY.md](SECURITY.md) for findings, boundaries and verification limits, and [integration setup](integrations/mac-companion/README.md) for installation. [UPSTREAM.md](UPSTREAM.md) is preserved historical upstream documentation; its MCP cookie-pasting and Keychain-write instructions do not apply to this fork.
