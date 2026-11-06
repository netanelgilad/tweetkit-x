# Shared Mac companion installation

This module targets the existing `mac-companion` architecture, not a standalone network service. The `tweetkit-x` and `mac-companion` repositories must be siblings. Install Python dependencies into `tweetkit-x/.venv` from the hash-locked requirements file.

Copy this directory's `server.mjs`, `app/` and `test/` into `mac-companion/modules/tweetkit/`. Copy `x-session.mjs` into `mac-companion/modules/chrome/`.

In `modules/chrome/server.mjs`, import `readXSession` from `./x-session.mjs` and add this internal-only method before returning the server:

```js
server.readXSession = () => readXSession((op,input) =>
  bridge.dispatch(op,input,'tweetkit-local-session'));
```

In the root companion server's optional modules, after Chrome:

```js
['tweetkit', async () => (await import('./modules/tweetkit/server.mjs'))
  .createTweetkitServer({session: () => extra.chrome?.readXSession()})],
```

Do not expose `readXSession` as an RPC tool. It is a local secret handoff. The companion authenticates `/tweetkit/rpc` with its module-scoped registry and rejects browser Origin headers. The X account must use companion ID `tweetkit-personal`. The first status/read pins the X user ID in private companion state; writes refuse an unpinned identity. A local operator must intentionally remove the identity pin before changing accounts.

Run `node --test modules/tweetkit/test/`, the companion smoke tests and its existing tests. Type-check the app against its pinned `apps` version. Deploy it using the companion's normal app deployment helper, activate the module with the normal supervised restart, and link the `bridge` user account using `scripts/link-account.mjs`. Check Chrome and WhatsApp after restarting. No separate server, listener, tunnel or LaunchAgent is needed.

The registry bearer is a trusted service credential: it authorizes this module's full operation set. Executor enforces user-facing write approvals; the companion does not cryptographically attest those approvals. Do not share the bridge account with untrusted apps or users. Session errors, network challenges and ambiguous writes are never retried automatically.
