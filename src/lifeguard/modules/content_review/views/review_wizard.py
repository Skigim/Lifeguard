"""Multi-step review wizard view."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Coroutine, Any

import discord

from lifeguard.modules.content_review.models import ReviewNote
from lifeguard.modules.content_review.views.note_modal import NoteModal

if TYPE_CHECKING:
    from lifeguard.modules.content_review.config import (
        ContentReviewConfig,
        ReviewCategory,
    )
    from lifeguard.modules.content_review.models import Submission


@dataclass
class DraftReview:
    """In-progress review state."""

    submission_id: str
    reviewer_id: int
    submitter_id: int
    guild_id: int
    current_step: int = 0
    scores: dict[str, int] = field(default_factory=dict)
    notes: dict[str, ReviewNote] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewWizardView(discord.ui.View):
    """Multi-step wizard for reviewing submissions."""

    def __init__(
        self,
        config: ContentReviewConfig,
        submission: Submission,
        reviewer_id: int,
        on_publish_callback: Callable[[DraftReview], Coroutine[Any, Any, None]],
        timeout: float = 900.0,  # 15 minutes default
    ) -> None:
        super().__init__(timeout=timeout)
        self.config = config
        self.submission = submission
        self.on_publish_callback = on_publish_callback

        # Initialize draft review
        self.draft = DraftReview(
            submission_id=submission.id,
            reviewer_id=reviewer_id,
            submitter_id=submission.submitter_id,
            guild_id=submission.guild_id,
        )

        self._message: discord.Message | None = None
        self._update_components()

    @property
    def categories(self) -> list[ReviewCategory]:
        return self.config.review_categories

    @property
    def current_category(self) -> ReviewCategory | None:
        if 0 <= self.draft.current_step < len(self.categories):
            return self.categories[self.draft.current_step]
        return None

    @property
    def is_summary_step(self) -> bool:
        return self.draft.current_step >= len(self.categories)

    def _update_components(self) -> None:
        """Update view components based on current step."""
        self.clear_items()

        if self.is_summary_step:
            self._add_summary_components()
        else:
            self._add_category_components()

    def _add_category_components(self) -> None:
        """Add components for rating a category."""
        category = self.current_category
        if not category:
            return

        # Rating select menu
        current_score = self.draft.scores.get(category.id)
        options = [
            discord.SelectOption(
                label=str(i),
                value=str(i),
                default=(current_score == i),
            )
            for i in range(category.min_score, category.max_score + 1)
        ]

        select = discord.ui.Select(
            placeholder=f"Select score ({category.min_score}-{category.max_score})",
            options=options,
            custom_id="rating_select",
        )
        select.callback = self._on_rating_select
        self.add_item(select)

        # Note button (if enabled for this category)
        if category.allow_notes:
            has_note = category.id in self.draft.notes
            note_btn = discord.ui.Button(
                label="✅ Note" if has_note else "Add Note",
                style=discord.ButtonStyle.secondary,
                custom_id="add_note",
            )
            note_btn.callback = self._on_add_note
            self.add_item(note_btn)

        # Navigation buttons
        if self.draft.current_step > 0:
            back_btn = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="back",
            )
            back_btn.callback = self._on_back
            self.add_item(back_btn)

        is_last = self.draft.current_step == len(self.categories) - 1
        next_btn = discord.ui.Button(
            label="Review Summary" if is_last else "Next",
            style=discord.ButtonStyle.primary,
            custom_id="next",
            disabled=(current_score is None),  # Require score to proceed
        )
        next_btn.callback = self._on_next
        self.add_item(next_btn)

        # Cancel button
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="cancel",
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    def _add_summary_components(self) -> None:
        """Add components for summary/publish step."""
        edit_btn = discord.ui.Button(
            label="Edit",
            style=discord.ButtonStyle.secondary,
            custom_id="edit",
        )
        edit_btn.callback = self._on_edit
        self.add_item(edit_btn)

        publish_btn = discord.ui.Button(
            label="Publish Review",
            style=discord.ButtonStyle.success,
            custom_id="publish",
        )
        publish_btn.callback = self._on_publish
        self.add_item(publish_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="cancel",
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    def build_embed(self) -> discord.Embed:
        """Build the current step's embed."""
        if self.is_summary_step:
            return self._build_summary_embed()
        return self._build_category_embed()

    def _build_category_embed(self) -> discord.Embed:
        """Build embed for rating a category."""
        category = self.current_category
        step = self.draft.current_step + 1
        total = len(self.categories)

        embed = discord.Embed(
            title=f"Step {step}/{total}: {category.name}",
            description=category.description or "Rate this category.",
            color=discord.Color.blue(),
        )

        # Show current score if set
        current_score = self.draft.scores.get(category.id)
        if current_score is not None:
            embed.add_field(
                name="Current Score", value=f"**{current_score}**", inline=True
            )

        # Show note preview if exists
        note = self.draft.notes.get(category.id)
        if note:
            preview = (
                note.feedback[:100] + "..."
                if len(note.feedback) > 100
                else note.feedback
            )
            embed.add_field(name="Note", value=preview, inline=False)

        # Progress indicator
        progress = " ".join(
            "✅" if cat.id in self.draft.scores else "⬜" for cat in self.categories
        )
        embed.set_footer(text=f"Progress: {progress}")

        return embed

    def _build_summary_embed(self) -> discord.Embed:
        """Build embed for review summary."""
        embed = discord.Embed(
            title="📋 Review Summary",
            description="Review your scores before publishing.",
            color=discord.Color.green(),
        )

        for category in self.categories:
            score = self.draft.scores.get(category.id, "N/A")
            note = self.draft.notes.get(category.id)

            value = f"**Score: {score}**"
            if note:
                preview = (
                    note.feedback[:80] + "..."
                    if len(note.feedback) > 80
                    else note.feedback
                )
                value += f"\n📝 {preview}"

            embed.add_field(name=category.name, value=value, inline=False)

        # Calculate average
        if self.draft.scores:
            avg = sum(self.draft.scores.values()) / len(self.draft.scores)
            embed.add_field(name="Average Score", value=f"**{avg:.1f}**", inline=True)

        return embed

    async def _on_rating_select(self, interaction: discord.Interaction) -> None:
        """Handle rating selection."""
        category = self.current_category
        if not category:
            return

        value = int(interaction.data["values"][0])
        self.draft.scores[category.id] = value

        self._update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_add_note(self, interaction: discord.Interaction) -> None:
        """Open note modal."""
        category = self.current_category
        if not category:
            return

        existing_note = self.draft.notes.get(category.id)

        async def on_note_submit(
            modal_interaction: discord.Interaction,
            reference: str,
            feedback: str,
        ) -> None:
            self.draft.notes[category.id] = ReviewNote(
                reference=reference,
                feedback=feedback,
            )
            self._update_components()
            await modal_interaction.response.edit_message(
                embed=self.build_embed(),
                view=self,
            )

        modal = NoteModal(
            category_name=category.name,
            on_submit_callback=on_note_submit,
            existing_reference=existing_note.reference if existing_note else "",
            existing_feedback=existing_note.feedback if existing_note else "",
        )
        await interaction.response.send_modal(modal)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        """Go to previous step."""
        self.draft.current_step = max(0, self.draft.current_step - 1)
        self._update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        """Go to next step."""
        self.draft.current_step += 1
        self._update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_edit(self, interaction: discord.Interaction) -> None:
        """Return to first step for editing."""
        self.draft.current_step = 0
        self._update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_publish(self, interaction: discord.Interaction) -> None:
        """Publish the review."""
        await interaction.response.defer()
        self.stop()
        await self.on_publish_callback(self.draft)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        """Cancel the review."""
        self.stop()
        await interaction.response.edit_message(
            content="❌ Review cancelled.",
            embed=None,
            view=None,
        )

    async def on_timeout(self) -> None:
        """Handle timeout."""
        if self._message:
            try:
                await self._message.edit(
                    content="⏰ Review timed out.",
                    embed=None,
                    view=None,
                )
            except discord.NotFound:
                pass
