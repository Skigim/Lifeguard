# Lifeguard Feature Catalogue

This document outlines the current capabilities and modules available in the Lifeguard Discord Bot. Lifeguard operates on a modular architecture, meaning server administrators can enable or disable specific features as needed.

## ⚙️ Core functionality
These commands and tools are built into the backbone of the bot for administration and health monitoring.
* **/ping:** Basic health check to ensure the bot is online and responding.
* **/config setup:** Interactive administrative UI for setting up features and enabling/disabling individual modules per-server.
* **/config status:** Provides an overview of the server's current Configuration, including which modules are enabled and their status.
* **/config disable:** Allows administrators to quickly disable specific modules on the server.

---

## 🕒 Time Impersonator
A module designed to eliminate international scheduling confusion.
* **/t [message]:** Takes a message containing a natural language time (e.g., "See you at 5pm EST!") and replaces it with a universal Discord timestamp that automatically adjusts to every reader's local timezone. The bot uses webhooks to "impersonate" the user, preserving their display name and avatar so it looks like they sent the message directly.
* **/tz set:** Allows users to explicitly lock in their prevailing timezone for the bot to use as a baseline when calculating their time inputs.

---

## 🎙️ Voice Lobbies
A dynamic channel management system to keep server channel lists clean and clutter-free.
* **Auto-Creation:** Users join a designated "Lobby" channel, and the bot immediately creates a temporary, private voice channel and text channel specifically for them.
* **Auto-Move:** The user is seamlessly moved into their new temporary channel.
* **Auto-Cleanup:** Once the channel is empty, the bot automatically deletes it to avoid clutter. 

---

## 📝 Content Review
A robust ticketing and review system tailored for content ingestion and feedback, powered by interactive Discord UI components (Modals & Sticky Messages).
* **/submit:** Generates a guided submission modal for users to submit content for review. This opens a dedicated ticket channel under a designated category.
* **Interactive Review Wizard:** Gives designated reviewers an interactive menu inside the ticket to add notes, rate content, require edits, or approve/publish the item.
* **/close-ticket:** Specifically shuts down the active review ticket channel.
* **/leaderboard:** Displays a ranking of the most active reviewers in the server.
* **/review-profile:** Let a reviewer check their individual statistics and contribution history.
* **Sticky Navigation:** Persists important navigational buttons or menus at the bottom of active ticket channels so reviewers always have access to the controls.

---

## ⚔️ Albion Online Integrations
A utility module for fetching and displaying data from the Albion Online API.
* **/search:** Retrieves standard Albion player or guild statistics.
* **/build:** Look up specific saved loadouts/builds via an ID directly within Discord.
