"""Embed builders for Content Review module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from lifeguard.modules.content_review.config import ContentReviewConfig
    from lifeguard.modules.content_review.models import (
        ReviewSession,
        Submission,
        UserProfile,
    )


def build_submission_embed(
    submission: Submission,
    config: ContentReviewConfig,
    submitter: discord.User | discord.Member,
) -> discord.Embed:
    """Build the embed displayed in the submission channel."""
    # Format title/description with placeholders
    title = config.ticket_title.format(
        user=submitter.display_name,
        submission_id=submission.id,
    )
    description = config.ticket_description.format(
        user=submitter.display_name,
        submission_id=submission.id,
    )

    embed = discord.Embed(
        title=title,
        description=description if description else None,
        color=discord.Color.blue(),
        timestamp=submission.created_at,
    )

    embed.set_author(
        name=submitter.display_name,
        icon_url=submitter.display_avatar.url if submitter.display_avatar else None,
    )

    # Add each field from the submission
    for field_config in config.submission_fields:
        value = submission.fields.get(field_config.id, "")
        if value:
            # Truncate long values
            if len(value) > 1024:
                value = value[:1021] + "..."
            embed.add_field(
                name=field_config.label,
                value=value,
                inline=False,
            )

    embed.set_footer(text=f"Submission ID: {submission.id}")
    return embed


def build_review_embed(
    review: ReviewSession,
    config: ContentReviewConfig,
    reviewer: discord.User | discord.Member,
    submitter: discord.User | discord.Member,
) -> discord.Embed:
    """Build the embed for a published review."""
    avg_score = review.average_score()

    # Color based on score
    if avg_score >= 4.0:
        color = discord.Color.green()
    elif avg_score >= 2.5:
        color = discord.Color.gold()
    else:
        color = discord.Color.red()

    embed = discord.Embed(
        title="📝 Review Complete",
        description=f"Review for {submitter.mention}",
        color=color,
        timestamp=review.completed_at or review.created_at,
    )

    embed.set_author(
        name=f"Reviewed by {reviewer.display_name}",
        icon_url=reviewer.display_avatar.url if reviewer.display_avatar else None,
    )

    # Add scores for each category
    for category in config.review_categories:
        score = review.scores.get(category.id)
        note = review.notes.get(category.id)

        if score is not None:
            # Visual score bar
            filled = "█" * score
            empty = "░" * (category.max_score - score)
            score_bar = f"`{filled}{empty}` **{score}/{category.max_score}**"

            value = score_bar
            if note:
                if note.reference:
                    value += f"\n> 📍 *{note.reference}*"
                value += f"\n> {note.feedback}"

            embed.add_field(name=category.name, value=value, inline=False)

    # Average score
    embed.add_field(
        name="📊 Overall",
        value=f"**{avg_score:.1f}** average",
        inline=True,
    )

    return embed


def build_leaderboard_embed(
    profiles: list[UserProfile],
    guild: discord.Guild,
) -> discord.Embed:
    """Build the reviewer leaderboard embed."""
    embed = discord.Embed(
        title="🏆 Reviewer Leaderboard",
        color=discord.Color.gold(),
    )

    if not profiles:
        embed.description = "No reviews have been completed yet!"
        return embed

    lines = []
    medals = ["🥇", "🥈", "🥉"]

    for i, profile in enumerate(profiles[:10]):
        medal = medals[i] if i < 3 else f"**{i + 1}.**"
        member = guild.get_member(profile.user_id)
        name = member.display_name if member else f"User {profile.user_id}"

        lines.append(f"{medal} {name} — **{profile.total_reviews_given}** reviews")

    embed.description = "\n".join(lines)
    return embed


def build_profile_embed(
    profile: UserProfile,
    config: ContentReviewConfig,
    user: discord.User | discord.Member,
) -> discord.Embed:
    """Build a user's profile embed."""
    embed = discord.Embed(
        title=f"📊 {user.display_name}'s Profile",
        color=discord.Color.blue(),
    )

    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)

    embed.add_field(
        name="Submissions",
        value=str(profile.total_submissions),
        inline=True,
    )
    embed.add_field(
        name="Reviews Given",
        value=str(profile.total_reviews_given),
        inline=True,
    )
    embed.add_field(
        name="Average Score",
        value=f"{profile.average_score:.2f}" if profile.average_score else "N/A",
        inline=True,
    )

    # Category breakdown if available
    if profile.category_averages:
        breakdown_lines = []
        for category in config.review_categories:
            avg = profile.category_averages.get(category.id)
            if avg is not None:
                breakdown_lines.append(f"**{category.name}:** {avg:.1f}")

        if breakdown_lines:
            embed.add_field(
                name="Category Averages",
                value="\n".join(breakdown_lines),
                inline=False,
            )

    # Badges
    if profile.badges:
        embed.add_field(
            name="Badges",
            value=" ".join(profile.badges),
            inline=False,
        )

    return embed
