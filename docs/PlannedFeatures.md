# Planned Features

## Application Ticket Management
- **Generalized Ticket Module**: Expand and rescope the current `content_review` cog to act as a generalized ticketing solution.
  - *Key Features*:
    - Handle standard server applications (e.g. guild recruitment, guild role apps).
    - Automatic role assignment upon approval/acceptance.
    - Customizable intake modals/forms based on the application type.
  - *Required Permissions*: **Manage Channels** (to create/close tickets), **Manage Roles** (for automatic assignment).

## RemindMe Module
- **User Reminders**: Allow users to set personalized timed reminders.
  - *Key Features*:
    - `/remindme [time] [message]`: Users can set a reminder to be delivered via DM or an inline ephemeral ping.
    - Contextual reminders via message replies (e.g., right-clicking/replying to a message to fire a reminder linked directly back to that specific message context).
  - *Required Permissions*: Base text permissions (Send Messages, Embed Links), possibly **Read Message History** to fetch context for message replies.

## Time Impersonator
- **Thread Support**: Allow the `/t` command to be used inside Discord threads.
  - *Technical Details*:
    - Update the channel type check to allow `discord.Thread`.
    - Fetch/create the webhook on the thread's parent channel (`thread.parent`).
    - Send the webhook message targeting the specific thread.
  - *Required Permissions*: **Send Messages in Threads**, **Manage Webhooks** (on the parent channel).
