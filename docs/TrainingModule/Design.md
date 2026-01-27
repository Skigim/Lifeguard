# Training Module Design Specification

A configurable submission and review system for Discord communities. This module enables users to submit content for peer or mentor review using a multi-step wizard interface.

---

## 1. Configuration

The module is driven by a configuration schema that defines the review workflow. Server administrators can customize categories, scoring, and validation rules.

### Configuration Schema

```python
@dataclass
class ReviewCategory:
    id: str                    # Unique identifier (e.g., "category_1")
    name: str                  # Display name (e.g., "Communication")
    description: str           # Tooltip/help text
    min_score: int = 1         # Minimum rating value
    max_score: int = 5         # Maximum rating value
    allow_notes: bool = True   # Whether reviewers can add notes

@dataclass
class SubmissionField:
    id: str                    # Unique identifier
    label: str                 # Display label
    field_type: str            # "short_text", "paragraph", or "url"
    required: bool = True
    placeholder: str = ""
    validation_regex: str = "" # Optional regex for validation

@dataclass
class TrainingModuleConfig:
    submission_channel_id: int         # Where submissions are posted
    reviewer_role_ids: list[int]       # Roles allowed to review
    submission_fields: list[SubmissionField]
    review_categories: list[ReviewCategory]
    dm_on_complete: bool = True        # DM submitter when review is done
    leaderboard_enabled: bool = True
```

---

## 2. Slash Commands

### `/submit`

**Description:** Opens the submission modal for users to submit content for review.

**Permissions:** Public (or configurable via role restrictions).

**Action:** Triggers `MODAL_SUBMISSION` with fields defined in configuration.

### `/leaderboard`

**Description:** Displays reviewer rankings based on completed reviews.

**Permissions:** Public.

### `/training-config` (Admin)

**Description:** Configure the training module settings.

**Permissions:** Administrator only.

---

## 3. Interaction Flows

### A. Submission Flow

**Trigger:** User runs `/submit`.

**Modal (`MODAL_SUBMISSION`):**
- Dynamically generated from `submission_fields` configuration
- Each field rendered based on its `field_type`
- Validation applied using `validation_regex` if specified

**Output:**
- Bot posts an embed to the configured submission channel
- Embed displays: Submitter info, all field values, timestamp
- Attached button: `BTN_START_REVIEW` (Label: "Start Review", Style: Success)

### B. Review Wizard

**Trigger:** Reviewer with appropriate role clicks `BTN_START_REVIEW`.

**State Management:**
- Temporary store (in-memory dict or Redis) holds draft review
- Key: `{reviewer_id}_{submission_id}` → `DraftReview` object
- Auto-expires after configurable timeout (default: 15 minutes)

**Wizard Flow (iterates through configured categories):**

**Ephemeral Message (visible only to reviewer):**
- Embed showing: `"Step {current}/{total}: {category.name}"`
- Category description displayed for context
- Select Menu: `SELECT_RATING` with options from `min_score` to `max_score`

**Button Row:**
- `BTN_ADD_NOTE` (Label: "Add Note", Style: Secondary) - if `allow_notes` is True
- `BTN_BACK` (Label: "Back", disabled on first step)
- `BTN_NEXT` (Label: "Next" or "Finish" on last step)

**Actions:**
- **Select Menu:** Updates draft score for current category
- **BTN_ADD_NOTE:** Opens `MODAL_NOTE` with:
  - Input 1: `reference` (Short Text, e.g., timestamp or section)
  - Input 2: `feedback` (Paragraph)
  - On submit: Saves to draft, shows ✅ indicator on ephemeral message
- **BTN_NEXT:** Advances to next category or summary view

### C. Summary & Publish

**Trigger:** `BTN_NEXT` clicked on final category.

**Summary View:**
- Ephemeral message shows read-only summary of all scores and notes
- Category-by-category breakdown with visual score representation

**Buttons:**
- `BTN_EDIT` (Label: "Edit", Style: Secondary) - Returns to step 1
- `BTN_PUBLISH` (Label: "Publish Review", Style: Success)

**Publish Action:**
1. Fetches original submission message
2. Posts public reply embed with complete review
3. (Optional) DMs submitter with results if `dm_on_complete` is True
4. Updates database: submitter stats, reviewer stats
5. Clears draft from temporary storage

---

## 4. Data Models

### Submission

```python
@dataclass
class Submission:
    id: str
    guild_id: int
    channel_id: int
    message_id: int
    submitter_id: int
    fields: dict[str, str]     # field_id -> value
    status: str                # "pending", "in_review", "completed"
    created_at: datetime
```

### Review Session

```python
@dataclass
class ReviewSession:
    id: str
    submission_id: str
    reviewer_id: int
    submitter_id: int
    scores: dict[str, int]     # category_id -> score
    notes: dict[str, ReviewNote]  # category_id -> note
    created_at: datetime
    completed_at: datetime | None

@dataclass
class ReviewNote:
    reference: str             # Timestamp, section, or context
    feedback: str
```

### User Profile

```python
@dataclass
class UserProfile:
    user_id: int
    guild_id: int
    total_submissions: int
    total_reviews_given: int
    average_score: float       # Running average across all categories
    category_averages: dict[str, float]  # category_id -> average
    badges: list[str]          # Achievement badges
    submission_history: list[SubmissionSummary]
```

---

## 5. Implementation Notes

### Discord.py Patterns

- **Ephemeral Updates:** The entire wizard flow uses a single ephemeral message. Use `interaction.response.edit_message()` to update content as the reviewer progresses. Never send new messages per step.

- **View Timeouts:** Set view timeout to ~15 minutes. On timeout, clean up the draft state and optionally notify the reviewer.

- **Modal Limitations:** Discord modals cannot contain select menus. Keep rating dropdowns on the ephemeral message; modals are only for text input (notes).

- **Custom IDs:** Use structured custom IDs for stateful components:
  ```
  review:{submission_id}:{action}:{step}
  ```

### Validation

For URL fields, apply validation regex at modal submission time:
```python
# Generic URL pattern
url_pattern = r'^https?:\/\/[\w\-\.]+\.[a-z]{2,}(\/\S*)?$'

# Or allow configuration per field
field.validation_regex
```

### Extensibility

The configuration-driven design allows:
- Adding new categories without code changes
- Customizing submission fields per server
- Adjusting scoring scales per category
- Enabling/disabling features like notes or DMs