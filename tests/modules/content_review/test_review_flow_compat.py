import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from lifeguard.features.forms.models import FormResponseSession
from lifeguard.features.forms.schema import FormCategory, FormField, ScoreOptions
from lifeguard.modules.content_review.config import ContentReviewConfig
from lifeguard.modules.content_review.forms_translation import ReviewPayload
from lifeguard.modules.content_review.models import ReviewNote, Submission


class ContentReviewFlowCompatTests(unittest.IsolatedAsyncioTestCase):
    def _build_config(self) -> ContentReviewConfig:
        return ContentReviewConfig(
            guild_id=123,
            enabled=True,
            submission_fields=[
                FormField(
                    id="game_link",
                    label="Game Link",
                    field_type="url",
                    required=True,
                )
            ],
            form_categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    response_kind="score",
                    options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
                )
            ],
            review_timeout_minutes=20,
            modal_title="Submit for Review",
            dm_on_complete=True,
        )

    def _build_interaction(
        self,
        *,
        guild: object,
        user_id: int,
        user_name: str = "Reviewer",
    ) -> SimpleNamespace:
        original_message = MagicMock()
        response = SimpleNamespace(
            send_message=AsyncMock(),
            send_modal=AsyncMock(),
            edit_message=AsyncMock(),
            defer=AsyncMock(),
        )
        return SimpleNamespace(
            guild=guild,
            user=SimpleNamespace(id=user_id, name=user_name),
            response=response,
            original_response=AsyncMock(return_value=original_message),
            edit_original_response=AsyncMock(),
        )

    async def test_handle_submit_button_uses_shared_submission_modal(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        bot = SimpleNamespace(lifeguard_firestore=object())
        cog = ContentReviewCog(bot)
        config = self._build_config()
        interaction = self._build_interaction(
            guild=SimpleNamespace(id=123),
            user_id=456,
            user_name="submitter",
        )
        sentinel_modal = object()

        with patch(
            "lifeguard.modules.content_review.cog.repo.get_config",
            return_value=config,
        ), patch(
            "lifeguard.modules.content_review.cog.FormSubmissionModal",
            create=True,
            return_value=sentinel_modal,
        ) as shared_modal_cls, patch(
            "lifeguard.modules.content_review.cog.SubmissionModal",
            create=True,
        ) as legacy_modal_cls:
            await cog._handle_submit_button(interaction)

        shared_modal_cls.assert_called_once()
        legacy_modal_cls.assert_not_called()
        self.assertEqual(shared_modal_cls.call_args.args[0], config.modal_title)
        self.assertEqual(shared_modal_cls.call_args.args[1], config.submission_fields)
        self.assertTrue(callable(shared_modal_cls.call_args.args[2]))
        interaction.response.send_modal.assert_awaited_once_with(sentinel_modal)

    async def test_handle_submit_button_with_oversized_config_returns_ephemeral_error(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        bot = SimpleNamespace(lifeguard_firestore=object())
        cog = ContentReviewCog(bot)
        config = self._build_config()
        config.submission_fields = [
            FormField(
                id=f"field_{index}",
                label=f"Field {index}",
                field_type="short_text",
                required=True,
            )
            for index in range(1, 7)
        ]
        interaction = self._build_interaction(
            guild=SimpleNamespace(id=123),
            user_id=456,
            user_name="submitter",
        )

        with patch(
            "lifeguard.modules.content_review.cog.repo.get_config",
            return_value=config,
        ):
            try:
                await cog._handle_submit_button(interaction)
            except Exception as exc:  # pragma: no cover - red-phase guard
                self.fail(f"_handle_submit_button raised unexpectedly: {exc!r}")

        interaction.response.send_modal.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "This submission form has too many fields to open in Discord. Please contact an administrator.",
            ephemeral=True,
        )

    async def test_start_review_uses_shared_form_wizard_with_session_draft(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        bot = SimpleNamespace(lifeguard_firestore=object())
        cog = ContentReviewCog(bot)
        config = self._build_config()
        submission = Submission(
            id="submission-1",
            guild_id=123,
            channel_id=999,
            message_id=1001,
            submitter_id=777,
            fields={"game_link": "https://example.invalid/replay"},
        )
        interaction = self._build_interaction(
            guild=SimpleNamespace(id=123),
            user_id=456,
        )
        session = FormResponseSession(
            id="content_review:submission-1:456",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-1",
            responder_id=456,
        )
        wizard = MagicMock()
        wizard.build_embed.return_value = object()

        with patch(
            "lifeguard.modules.content_review.cog.repo.get_config",
            return_value=config,
        ), patch(
            "lifeguard.modules.content_review.cog.repo.get_submission",
            return_value=submission,
        ), patch(
            "lifeguard.modules.content_review.cog.repo.claim_submission_for_review",
            return_value=submission,
        ), patch(
            "lifeguard.modules.content_review.cog.build_review_session_draft",
            create=True,
            return_value=session,
        ) as build_draft, patch(
            "lifeguard.modules.content_review.cog.FormWizardView",
            create=True,
            return_value=wizard,
        ) as shared_wizard_cls, patch(
            "lifeguard.modules.content_review.cog.ReviewWizardView",
            create=True,
        ) as legacy_wizard_cls:
            await cog._start_review(interaction, submission.id)

        build_draft.assert_called_once_with(
            submission_id=submission.id,
            guild_id=submission.guild_id,
            responder_id=interaction.user.id,
            categories=config.form_categories,
        )
        shared_wizard_cls.assert_called_once()
        self.assertEqual(shared_wizard_cls.call_args.kwargs["categories"], config.form_categories)
        self.assertIs(shared_wizard_cls.call_args.kwargs["session"], session)
        self.assertEqual(
            shared_wizard_cls.call_args.kwargs["timeout"],
            config.review_timeout_minutes * 60,
        )
        self.assertTrue(callable(shared_wizard_cls.call_args.kwargs["on_publish_callback"]))
        legacy_wizard_cls.assert_not_called()
        interaction.response.send_message.assert_awaited_once_with(
            embed=wizard.build_embed.return_value,
            view=wizard,
            ephemeral=True,
        )
        interaction.original_response.assert_awaited_once_with()
        wizard.attach_message.assert_called_once_with(
            interaction.original_response.return_value
        )
        self.assertIs(cog._pending_reviews[f"{interaction.user.id}:{submission.id}"], wizard)

    async def test_start_review_preserves_reviewer_facing_wizard_copy(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        bot = SimpleNamespace(lifeguard_firestore=object())
        cog = ContentReviewCog(bot)
        config = self._build_config()
        submission = Submission(
            id="submission-1",
            guild_id=123,
            channel_id=999,
            message_id=1001,
            submitter_id=777,
            fields={"game_link": "https://example.invalid/replay"},
        )
        interaction = self._build_interaction(
            guild=SimpleNamespace(id=123),
            user_id=456,
        )

        with patch(
            "lifeguard.modules.content_review.cog.repo.get_config",
            return_value=config,
        ), patch(
            "lifeguard.modules.content_review.cog.repo.get_submission",
            return_value=submission,
        ), patch(
            "lifeguard.modules.content_review.cog.repo.claim_submission_for_review",
            return_value=submission,
        ):
            await cog._start_review(interaction, submission.id)

        wizard = interaction.response.send_message.await_args.kwargs["view"]
        self.assertEqual(interaction.response.send_message.await_args.kwargs["embed"].title, "Step 1/1: Overall")
        self.assertEqual(
            interaction.response.send_message.await_args.kwargs["embed"].description,
            "Rate this category.",
        )

        select = next(item for item in wizard.children if isinstance(item, discord.ui.Select))
        self.assertEqual(select.placeholder, "Select score (1-5)")

        note_buttons = [
            item
            for item in wizard.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_open_modal"
        ]
        self.assertEqual(note_buttons, [])

        next_button = next(
            item
            for item in wizard.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_next"
        )
        self.assertEqual(next_button.label, "Review Summary")

        select_interaction = MagicMock()
        select_interaction.data = {"values": ["4"]}
        select_interaction.response.edit_message = AsyncMock()
        await wizard._on_select_submit(select_interaction)

        note_button = next(
            item
            for item in wizard.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_open_modal"
        )
        self.assertEqual(note_button.label, "Add Note")

        open_modal_interaction = MagicMock()
        open_modal_interaction.response.send_modal = AsyncMock()
        await wizard._on_open_modal(open_modal_interaction)

        modal = open_modal_interaction.response.send_modal.await_args.args[0]
        modal._field_inputs["reference"]._value = "Clip 00:12"
        modal._field_inputs["note"]._value = "Solid progress"
        modal_interaction = MagicMock()
        modal_interaction.response.edit_message = AsyncMock()
        await modal.on_submit(modal_interaction)

        note_button = next(
            item
            for item in wizard.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_open_modal"
        )
        self.assertEqual(note_button.label, "✅ Note")

        next_interaction = MagicMock()
        next_interaction.response.edit_message = AsyncMock()
        await wizard._on_next(next_interaction)

        summary_embed = wizard.build_embed()
        self.assertEqual(summary_embed.title, "📋 Review Summary")
        self.assertEqual(
            summary_embed.description,
            "Review your scores before publishing.",
        )

        publish_button = next(
            item
            for item in wizard.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_publish"
        )
        self.assertEqual(publish_button.label, "Publish Review")

        cancel_interaction = MagicMock()
        cancel_interaction.response.edit_message = AsyncMock()
        await wizard._on_cancel(cancel_interaction)
        cancel_interaction.response.edit_message.assert_awaited_once_with(
            content="❌ Review cancelled.",
            embed=None,
            view=None,
        )

        wizard._message = MagicMock()
        wizard._message.edit = AsyncMock()
        await wizard.on_timeout()
        wizard._message.edit.assert_awaited_once_with(
            content="⏰ Review timed out.",
            embed=None,
            view=None,
        )

    async def test_publish_review_translates_shared_session_to_legacy_review_record(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        submitter = MagicMock()
        submitter.send = AsyncMock()
        bot = SimpleNamespace(
            lifeguard_firestore=object(),
            fetch_user=AsyncMock(return_value=submitter),
        )
        cog = ContentReviewCog(bot)
        config = self._build_config()
        submission = Submission(
            id="submission-1",
            guild_id=123,
            channel_id=999,
            message_id=1001,
            submitter_id=777,
            fields={"game_link": "https://example.invalid/replay"},
        )
        session = FormResponseSession(
            id="content_review:submission-1:456",
            guild_id=123,
            feature_key="content_review",
            owner_id=submission.id,
            responder_id=456,
            status="completed",
        )
        session.reviewer_id = 999
        session.submitter_id = 555
        session.scores = {"wrong": 1}
        session.notes = {}

        channel = MagicMock(spec=discord.TextChannel)
        original_message = MagicMock()
        original_message.reply = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=original_message)
        guild = SimpleNamespace(
            id=123,
            name="Lifeguard Guild",
            get_channel=MagicMock(return_value=channel),
        )
        interaction = self._build_interaction(guild=guild, user_id=456)
        embed = discord.Embed(title="Review")
        submitter_profile = MagicMock()
        reviewer_profile = SimpleNamespace(total_reviews_given=0)
        translated_payload = ReviewPayload(
            scores={"overall": 4},
            notes={
                "overall": ReviewNote(
                    reference="01:23",
                    feedback="Solid progress",
                )
            },
        )

        with patch(
            "lifeguard.modules.content_review.cog.session_to_review_payload",
            create=True,
            return_value=translated_payload,
        ) as translate_payload, patch(
            "lifeguard.features.forms.repo.save_session"
        ), patch(
            "lifeguard.modules.content_review.cog.repo.create_review"
        ) as create_review, patch(
            "lifeguard.modules.content_review.cog.repo.update_submission"
        ) as update_submission, patch(
            "lifeguard.modules.content_review.cog.repo.get_or_create_profile",
            side_effect=[submitter_profile, reviewer_profile],
        ), patch(
            "lifeguard.modules.content_review.cog.repo.save_profile"
        ) as save_profile, patch(
            "lifeguard.modules.content_review.cog.build_review_embed",
            return_value=embed,
        ):
            await cog._publish_review(interaction, config, submission, session)

        translate_payload.assert_called_once_with(session)
        created_review = create_review.call_args.args[1]
        self.assertEqual(created_review.submission_id, submission.id)
        self.assertEqual(created_review.guild_id, submission.guild_id)
        self.assertEqual(created_review.reviewer_id, session.responder_id)
        self.assertEqual(created_review.submitter_id, submission.submitter_id)
        self.assertEqual(created_review.scores, translated_payload.scores)
        self.assertEqual(created_review.notes, translated_payload.notes)
        self.assertEqual(submission.status, "completed")
        self.assertEqual(submission.reviewer_id, session.responder_id)
        update_submission.assert_called_once_with(cog.firestore, submission)
        submitter_profile.update_with_review.assert_called_once_with(created_review)
        self.assertEqual(reviewer_profile.total_reviews_given, 1)
        self.assertEqual(save_profile.call_count, 2)
        channel.fetch_message.assert_awaited_once_with(submission.message_id)
        original_message.reply.assert_awaited_once_with(embed=embed)
        submitter.send.assert_awaited_once_with(
            content="Your submission in **Lifeguard Guild** has been reviewed!",
            embed=embed,
        )
        interaction.edit_original_response.assert_awaited_once_with(
            content="✅ Review published successfully!",
            embed=None,
            view=None,
        )

    async def test_publish_review_saves_completed_generic_form_session_after_legacy_persistence(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        submitter = MagicMock()
        submitter.send = AsyncMock()
        bot = SimpleNamespace(
            lifeguard_firestore=object(),
            fetch_user=AsyncMock(return_value=submitter),
        )
        cog = ContentReviewCog(bot)
        config = self._build_config()
        submission = Submission(
            id="submission-1",
            guild_id=123,
            channel_id=999,
            message_id=1001,
            submitter_id=777,
            fields={"game_link": "https://example.invalid/replay"},
        )
        session = FormResponseSession(
            id="content_review:submission-1:456",
            guild_id=123,
            feature_key="content_review",
            owner_id=submission.id,
            responder_id=456,
        )

        channel = MagicMock(spec=discord.TextChannel)
        original_message = MagicMock()
        original_message.reply = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=original_message)
        guild = SimpleNamespace(
            id=123,
            name="Lifeguard Guild",
            get_channel=MagicMock(return_value=channel),
        )
        interaction = self._build_interaction(guild=guild, user_id=456)
        call_sequence: list[str] = []

        with patch(
            "lifeguard.modules.content_review.cog.session_to_review_payload",
            create=True,
            return_value=ReviewPayload(scores={}, notes={}),
        ), patch(
            "lifeguard.features.forms.repo.save_session",
            side_effect=lambda *_args, **_kwargs: call_sequence.append("save_session"),
        ) as save_session, patch(
            "lifeguard.modules.content_review.cog.repo.create_review",
            side_effect=lambda *_args, **_kwargs: call_sequence.append("create_review"),
        ), patch(
            "lifeguard.modules.content_review.cog.repo.update_submission",
            side_effect=lambda *_args, **_kwargs: call_sequence.append("update_submission"),
        ), patch(
            "lifeguard.modules.content_review.cog.repo.get_or_create_profile",
            side_effect=[MagicMock(), SimpleNamespace(total_reviews_given=0)],
        ), patch(
            "lifeguard.modules.content_review.cog.repo.save_profile",
            side_effect=lambda *_args, **_kwargs: call_sequence.append("save_profile"),
        ), patch(
            "lifeguard.modules.content_review.cog.build_review_embed",
            return_value=discord.Embed(title="Review"),
        ):
            await cog._publish_review(interaction, config, submission, session)

        self.assertEqual(session.status, "completed")
        self.assertIsNotNone(session.completed_at)
        save_session.assert_called_once_with(cog.firestore, session)
        self.assertEqual(
            call_sequence,
            [
                "create_review",
                "update_submission",
                "save_profile",
                "save_profile",
                "save_session",
            ],
        )

    async def test_publish_review_does_not_complete_generic_session_when_legacy_review_save_fails(self) -> None:
        from lifeguard.modules.content_review.cog import ContentReviewCog

        bot = SimpleNamespace(
            lifeguard_firestore=object(),
            fetch_user=AsyncMock(),
        )
        cog = ContentReviewCog(bot)
        config = self._build_config()
        submission = Submission(
            id="submission-1",
            guild_id=123,
            channel_id=999,
            message_id=1001,
            submitter_id=777,
            fields={"game_link": "https://example.invalid/replay"},
        )
        session = FormResponseSession(
            id="content_review:submission-1:456",
            guild_id=123,
            feature_key="content_review",
            owner_id=submission.id,
            responder_id=456,
        )
        original_completed_at = session.completed_at
        interaction = self._build_interaction(
            guild=SimpleNamespace(id=123, name="Lifeguard Guild"),
            user_id=456,
        )

        with patch(
            "lifeguard.modules.content_review.cog.session_to_review_payload",
            create=True,
            return_value=ReviewPayload(scores={}, notes={}),
        ), patch(
            "lifeguard.features.forms.repo.save_session"
        ) as save_session, patch(
            "lifeguard.modules.content_review.cog.repo.create_review",
            side_effect=RuntimeError("review create failed"),
        ), patch(
            "lifeguard.modules.content_review.cog.repo.update_submission"
        ) as update_submission:
            with self.assertRaisesRegex(RuntimeError, "review create failed"):
                await cog._publish_review(interaction, config, submission, session)

        save_session.assert_not_called()
        update_submission.assert_not_called()
        self.assertEqual(session.status, "draft")
        self.assertIs(session.completed_at, original_completed_at)
        self.assertEqual(submission.status, "pending")
        interaction.edit_original_response.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()