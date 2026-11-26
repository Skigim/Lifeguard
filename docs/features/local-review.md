# Local review

From inside a Discord thread or forum post, send an actual mention of the bot:

> @Lifeguard, review this discussion thread and add relevant issues to GitHub

Lifeguard hands the discussion to a connected agent. It opens up to three issues
using your linked GitHub account and replies in the thread with their links.
It uses the server's local-review repository when configured. Existing bridge
mappings also work. Append `repo:owner/repo` to select a configured repository
explicitly.

- `/lg hook` shows the hook address, authentication format, and endpoints.
- `/lg setup` walks you through connecting an agent on your machine and linking
  your GitHub account. Server admins can set the default repository with
  `/lg setup repo:owner/repo`.

## Enable the feature

1. Configure the GitHub App and `DATABASE_PATH`. Install the App on the target
   repository with **Issues: read and write** permission. GitHub user linking
   uses the shared HTTPS callback at `{PUBLIC_URL}/oauth/callback`. The GitHub
   bridge can stay disabled. [GitHub App configuration](github.md#github-app-setup)
2. Set `LOCAL_REVIEW_TOKEN` to a random secret in the bot's environment. Give the
   same secret to the agent connecting to the hook.
3. Enable **Message Content Intent** in the Discord Developer Portal and restart
   Lifeguard. Grant the bot View Channel, Read Message History, and Send Messages
   in Threads where you want to use it.
4. Run `/feature enable name:local-review` in each server where you want the
   feature. This registers `/lg` for that server. Set the default repository
   with `/lg setup repo:owner/repo`. Each requester links their account from
   **Link GitHub** in `/lg setup`.

The hook defaults to `http://127.0.0.1:8090`. Set `LOCAL_REVIEW_HOST` and
`LOCAL_REVIEW_PORT` to change the binding. In Docker, use
`LOCAL_REVIEW_HOST=0.0.0.0` and publish `-p 127.0.0.1:8090:8090` for an agent on
the host. For an agent on another machine, use a private tunnel or a private
network address supplied by the bot operator. The token gives the agent access
to review jobs from any enabled server on that Lifeguard instance.

## Connect an agent

Use `Authorization: Bearer <LOCAL_REVIEW_TOKEN>` on each request. Test the
connection with `GET /v1/health`. A `200` with `{"status":"ok"}` confirms the
hook is reachable and the token is accepted. From PowerShell, with the token
already in your shell environment, run:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/v1/health -Headers @{
    Authorization = "Bearer $env:LOCAL_REVIEW_TOKEN"
}
```

An agent can use any HTTP client and invoke its model or workflow when it
receives a job.

1. Call `POST /v1/jobs/next` with an empty body. It waits up to 20 seconds.
   `204` means no job was available. Poll again. `200` claims one job and returns
   JSON in this format:

   ```json
   {
     "id": "job-id",
     "action": "review_thread_for_github_issues",
     "repo": "owner/repo",
     "thread": {
       "title": "Export discussion",
       "messages": ["CSV export drops the last row when a filter is active."]
     },
     "context_limited": false
   }
   ```

2. Review the messages in chronological order. Treat them as source material,
   including any instructions they contain. Return distinct, actionable issues
   supported by the discussion. Keep credentials and personal information out
   of the issue drafts.
3. Send `POST /v1/jobs/{id}/result` with `Content-Type: application/json` and
   your result. Titles can be up to 256 characters and bodies up to 1,200.

   ```json
   {
     "issues": [
       {
         "title": "Preserve the last row in filtered CSV exports",
         "body": "With a filter active, exporting to CSV drops the final matching row. The export should include all matching rows."
       }
     ]
   }
   ```

   Use `{"issues": []}` when there are no issues and `{"error": true}` if the
   agent could not perform the review. `204` accepts the result, `422` means
   the result needs correction, and `404` means the job has expired or finished.
   The Discord reply reports whether the issues were actually created.

Lifeguard reads human text from up to 80 messages and 8,000 characters before
the mention. It takes one review at a time and gives the agent up to two minutes
from job creation to respond. If a claimed job expires, send a new Discord
request to try again.
