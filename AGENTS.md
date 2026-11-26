# Lifeguard architecture

- Lifeguard is the process host. It owns Discord startup, module discovery,
  command registration, enablement, and process lifecycles.
- Put new optional features in `src/lifeguard/plugins/`. Each feature declares
  its own process, cog, commands, and configuration. The host discovers
  installed modules on startup.
- Enable features independently per guild. Register feature slash commands
  only in enabled guilds and check enablement before processing Discord
  events or taking action. Start a shared feature process when its first
  guild enables it and stop it when its last guild disables it.
- Keep cogs independent. A feature can use a shared core service, but must
  work with other optional cogs disabled or removed. Keep feature-specific
  Discord commands and behavior inside that feature.
- Removing an optional module must leave startup and unrelated features
  working, including with an existing database. Reconcile previously
  registered guild commands when a module is removed.
- Apply this architecture to local review first. Migrate legacy cogs only
  when requested.

# Scope discipline

Never fetch, scan, crawl, or build new data sets unless explicitly asked to in
the current message. Authorization expires with the question it was given for.
A go-ahead from an earlier turn does not carry into the next question.

If new data would help, say so in one line and stop. Do not start gathering it.

Answer verification questions from the evidence already available. If it cannot
settle the question, say so. Stop the check when a disqualifying fact is found.

# Launching development apps

When asked to launch or restart an app under development, use the desktop app
launcher on the user's interactive desktop. A sandboxed shell or an escalated
shell command alone does not establish that the app is visible. Verify a real
desktop window before reporting a successful launch. If an earlier agent-launched
background instance blocks a single-instance lock, stop only that verified
instance before launching the app on the desktop.
