# GitHub bridge

Lifeguard mirrors GitHub issues and pull requests into a Discord forum. Each issue
or PR gets its own post. GitHub changes update the existing post or comment, and
linked Discord users can take explicit actions on GitHub from inside the thread.
The starter post shows **Recent GitHub activity** with up to five comments or
reviews received in the consolidated layout, plus the latest status notice.
Use each entry's **View** link to read it on GitHub. Discord discussion continues
below the starter post. Older individual mirrors stay where they were posted.

## Getting started in Discord

1. A server admin with **Manage Server** enables the feature with `/feature enable github`.
2. The admin uses `/bridge link-repo` to select an installed repository and its destination forum.
3. Run `/bridge backfill` to mirror currently open issues and PRs. With one linked
   repo, leave the repository field blank. With several, pick one from the suggestions.
   Backfill skips closed and merged items and does not import historical comments.
4. To act on GitHub from a thread, run `/github link` and authorize the GitHub App.
   GitHub applies your account's existing repository permissions.

## GitHub App setup

Create a GitHub App and install it on the repositories you want to bridge. Configure:

- Repository permissions: **Issues: read and write**, **Pull requests: read and write**,
  **Metadata: read**.
- Webhook content type: **application/json**, with a strong webhook secret.
- Events: `issues`, `issue_comment`, `pull_request`, `pull_request_review`,
  `pull_request_review_comment`, and `installation_repositories`.
- Webhook URL: `{PUBLIC_URL}/github/webhook`.
- User authorization callback URL: `{PUBLIC_URL}/oauth/callback`.
- Enable expiring user access tokens. Generate an app private key and a client secret.

Set `DATABASE_PATH`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH` (or the PEM in
`GITHUB_APP_PRIVATE_KEY`), `GITHUB_WEBHOOK_SECRET`, `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET`, `PUBLIC_URL`, and `TOKEN_ENCRYPTION_KEY` in your environment file.
Without `DATABASE_PATH`, other features use in-memory enablement. GitHub requires the database.
The SQLite file holds enablement, mappings, encrypted user tokens, and delivery history;
keep the Docker `/data` volume across deployments. Run one bot process per database/listener.

Expose the web listener with a stable public HTTPS URL, for example through Tailscale Funnel
forwarding to a Docker port published on loopback. For a temporary development
URL, run `cloudflared tunnel --url http://localhost:8080`, then copy its HTTPS URL into
`PUBLIC_URL` and both GitHub App URLs. Use a stable named tunnel or reverse proxy in production.
The listener defaults to `0.0.0.0:8080` (`WEB_HOST`/`WEB_PORT`); it starts when GitHub is enabled.
`GET /healthz` reports listener health. It does not verify Discord or GitHub connectivity.

### Token encryption key

Generate a key once:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Back up `TOKEN_ENCRYPTION_KEY` with the bot's other secrets. Never commit it.**
It encrypts every stored GitHub user token. Losing or changing it makes the stored tokens
unreadable and requires every user to run `/github link` again. Lifeguard removes an
unreadable account link and prompts that user to relink instead of crashing.

### Forum and commands

In the destination server, enable `/feature enable github`, then run
`/bridge link-repo owner/repo #forum`. The bot needs View Channel, Create Posts,
Send Messages in Threads, Manage Threads, Embed Links, and Read Message History.
If `Issue`, `PR`, `Open`, `Closed`, and `Merged` tags do not exist, it also needs
Manage Channels to create them. Alternatively create those five tags yourself.

- `/bridge repos`, `/bridge unlink-repo`, `/bridge backfill [repo]` manage mirrors.
  Backfill creates or refreshes all currently open items, without importing old comments.
- `/bridge map-label #forum label tag` maps a label to an existing tag (name or ID).
  Kind/state occupy two slots; at most three label tags follow. No label tags are auto-created.
- `/bridge bot-login add login collapse|human` overrides bot detection; `remove` clears it.
- `/github link`, `/github whoami`, `/github unlink` manage the user's authorization.
- `/comment`, `/close [reason]`, `/reopen` work inside linked threads under that user's identity.
- Use `/github edit-comment` or `/github delete-comment` and select your comment.
  For older individually mirrored messages, the **Edit on GitHub** and **Delete on GitHub**
  context menus are still available.
  Only the linked GitHub author can act. Deleting requires confirmation. Edit loads the current
  GitHub body, then offers an editor button. Bodies over Discord's 4,000-character modal
  limit must be edited on GitHub. Submitted reviews can be edited, but GitHub only permits
  deletion of pending reviews; use GitHub's review controls for submitted reviews.

Ordinary Discord chat never writes to GitHub. No message-content intent is required.
Closing archives a thread without locking it. Deleting an issue keeps the discussion,
adds a notice to the starter post, and locks/archives the thread. Bot *comments* use one-line summaries;
check runs and commit statuses are outside this bridge's scope.

### Delivery and recovery

Requests are signature-checked before enqueueing. Deliveries are marked processed only
after all enabled guild handlers succeed, and retained for seven days. A bounded in-memory
queue returns 503 when full. On startup, Lifeguard requests redelivery of unprocessed
deliveries still available from GitHub and reconciles changed issue/PR metadata using
the saved event cursor. Without a saved cursor, startup skips the metadata sweep.
Comments recover through webhook redelivery, not a comment crawl.
Failures are logged with delivery IDs and remain eligible for redelivery on restart;
an operator can also redeliver them through the GitHub App's delivery page.

Recovery is limited by GitHub's retained delivery history. A long outage can lose comments
outside that window. Discord writes and SQLite commits are not a distributed transaction:
a crash between a successful send and storing its mapping can produce a duplicate.
Mapped comments and successfully processed deliveries are deduplicated. Keep the database
and inspect delivery logs after an unclean shutdown.

### Verification

Run `ruff check src tests` and `pytest`. Tests use synthetic payload fixtures and mocked
GitHub/Discord clients, including signature rejection, OAuth expiry, encrypted token refresh,
author checks, echo suppression, deletion retention, recovery and persistent enablement.


For live verification, use a scratch repository and test Discord forum: open an issue and PR,
change labels, comment/edit/delete (including a bot comment), close/reopen/merge, then exercise
account linking and all thread actions. Confirm actions appear as the linked GitHub user and
another user cannot edit their comments. Delete a scratch issue and verify the thread remains
locked/archived. Stop the bot, comment on GitHub, restart, and verify recovery and enablement.
Live verification needs your configured GitHub App, Discord bot, HTTPS endpoint, and test guild.
