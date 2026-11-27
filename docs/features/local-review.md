# Local review

Once you have the server's configured Lifeguard role, start a message with a
Discord mention of Lifeguard, followed by your prompt.
Inside a thread or forum post, Lifeguard sends the recent discussion to the
agent along with your prompt. The agent's answer appears as a reply in Discord.

> @Lifeguard, review this thread and recommend a milestone title and checklist

You can also follow up on a Lifeguard message by replying to it, forwarding it,
pasting its Discord link, or quoting text from a recent Lifeguard reply in the
same server. Ask a question or make a request as you would with another person.
Sharing, quoting, or commenting on what Lifeguard said without addressing it
leaves the discussion alone.

A tag in the middle of a message can also invite a reply. If you tease Lifeguard,
it might react with an emoji or answer with a quick comeback. Neutral mentions
stay quiet. Start with a mention or follow up on a Lifeguard message for GitHub requests.

If you ask Lifeguard to post a comment on a GitHub pull request, it uses your
linked GitHub account and a repository configured for the server. Include the
PR number or link when the conversation leaves the target unclear. For Discord
message links across channels, Lifeguard can identify its message without
repeating text from the source channel.

To file GitHub issues, ask explicitly inside the discussion thread:

> @Lifeguard, review this discussion thread and add relevant issues to GitHub

Lifeguard opens up to three issues using your linked GitHub account and replies
in the thread with their links.
It uses the server's local-review repository when configured. Existing bridge
mappings also work. Append `repo:owner/repo` to select a configured repository
explicitly.

- `/lg config role:<role>` sets the server's required role for mentions and
  follow-ups. Run `/lg config` to view the current role. Both require **Manage
  Server** permission.
- `/lg hook` shows the hook address, authentication format, and endpoints.
- `/lg setup` walks you through connecting an agent on your machine and linking
  your GitHub account. Server admins can set the default repository with
  `/lg setup repo:owner/repo`.

## Enable the feature

1. Set `LOCAL_REVIEW_TOKEN` to a random secret in the bot's environment. Give the
   same secret to the agent connecting to the hook.
2. Enable **Message Content Intent** in the Discord Developer Portal and restart
   Lifeguard. Grant the bot View Channel, Read Message History, and Send Messages
   in Threads where you want it to review discussions.
3. Run `/feature enable name:local-review` in each server where you want the
   feature. This registers `/lg` for that server.
4. Use `/lg config` to select a role, then assign that role to members who should
   be able to use mentions and follow-ups. Lifeguard ignores these messages until
   a role is configured. Set `DATABASE_PATH` to keep the role setting across
   restarts.

To enable issue creation, configure `DATABASE_PATH` and install the GitHub App
on the target repository with **Issues: read and write** permission. Account
linking uses `{PUBLIC_URL}/oauth/callback`. Set the default repository with
`/lg setup repo:owner/repo` and link your account from **Link GitHub** in
`/lg setup`. [GitHub App configuration](github.md#github-app-setup)

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

1. Call `POST /v1/jobs/next?include_replies=true&include_references=true` with an empty body. It waits
   up to 20 seconds. `204` means no job was available. Poll again. `200` claims
   one job and returns JSON in this format:

   ```json
   {
     "id": "job-id",
     "action": "respond_to_prompt",
     "prompt": "Recommend a milestone title and checklist.",
     "thread": {
       "title": "Export discussion",
       "messages": ["CSV export drops the last row when a filter is active."]
     },
     "context_limited": false
   }
   ```

2. Answer `prompt` using `thread.messages` as source material in chronological
   order. The `thread` field is `null` for prompts sent outside a thread. Use
   the `action` to choose the result format. Keep credentials and personal
   information out of the response.
3. Send `POST /v1/jobs/{id}/result` with `Content-Type: application/json`.
   For `respond_to_prompt`, return `{"reply":"Your Discord reply"}` with up to
   1,900 characters. For `review_thread_for_github_issues`, the job includes
   `repo` and the result is an `issues` list. Draft up to three issues, each
   with a title up to 256 characters and a body up to 1,200.

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
   agent could not complete the request. `204` accepts the result, `422` means
   the result needs correction, and `404` means the job has expired or finished.
   Lifeguard posts the reply text or reports which issues were created.

Agents that poll `POST /v1/jobs/next` without the query parameter continue to
receive issue jobs in the original format.

With `include_references=true`, the agent can also receive `respond_to_reference`
jobs. The `prompt` field contains the new sender's words and `reference` contains
`kind`, `content`, and `mentioned`. Treat the reference as context for deciding
what the sender is asking. Return `action`, `text`, `repo`, `pr_number`, and
`issues`. Use `ignore` for passive discussion, `reply` for a Discord answer,
`react` for a single emoji (`🤨`, `🙄`, `😔`, `😂`, or `👀`) in `text`,
`create_issues` for an explicitly requested issue batch, and `post_pr_comment`
for an explicitly requested PR comment. Unused fields use empty strings, `null`,
or an empty list. Use `text` for the Discord reply or the PR comment body. Only
the new sender's request can authorize a GitHub write. For an inline tag with
`reference.kind` set to `mention`, only `ignore`, `reply`, and `react` are accepted.

Lifeguard reads human text from up to 80 messages and 8,000 characters before
the mention. It takes one review at a time and gives the agent up to two minutes
from job creation to respond. If a claimed job expires, send a new Discord
request to try again.
