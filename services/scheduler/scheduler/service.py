"""ReviewService: the single entry point (Facade) into the scheduler domain.

It owns cards, reviews and settings. Sentences and words belong to the content service and are
reached only through a ContentClient: to pull new sentences, to fetch a card's text, and to
score the placement quiz. If content does not answer, ContentUnavailable reaches the API,
which turns it into a 503; nothing the scheduler owns depends on content (ADR-6).
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta

from scheduler.algorithms import RATING_QUALITIES, SchedulingStrategy
from scheduler.content_client import ContentClient, FeedItem
from scheduler.models import (
    SENTENCE_CARD,
    WORD_CARD,
    Card,
    CardState,
    NewCard,
    NextReview,
    PlacementOutcome,
    Review,
    ReviewStats,
)
from scheduler.repository import CardRepository, ReviewLog, SettingsStore

DAILY_GOAL_KEY = "new_cards_per_day"
MIN_DAILY_GOAL = 1
MAX_DAILY_GOAL = 100
DAILY_GOAL_ERROR = f"Choose a goal between {MIN_DAILY_GOAL} and {MAX_DAILY_GOAL} new cards a day."

LEVEL_KEY = "level"
LEVEL_NAME_KEY = "level_name"
STARTER = (0, "Starter")      # the level a learner who skips the quiz starts at (content's LEVELS[0])
KNOWN_FIRST_CHECK_DAYS = 60   # cards skipped by the placement quiz come back after 2 months...
KNOWN_SPREAD_DAYS = 120       # ...spread over the next 4, so they never pile up on one day

PULL_SIZE = 20                # sentences asked for in one pull


class ReviewService:
    def __init__(self, card_repo: CardRepository, review_log: ReviewLog, settings: SettingsStore,
                 strategy: SchedulingStrategy, default_new_cards_per_day: int, content: ContentClient) -> None:
        self._cards = card_repo
        self._log = review_log
        self._settings = settings
        self._strategy = strategy
        self._default_new_cards_per_day = default_new_cards_per_day
        self._content = content

    # ----- daily goal -----

    def daily_goal(self) -> int | None:
        """The number of new cards a day the learner chose, or None before they choose."""
        stored = self._settings.get(DAILY_GOAL_KEY)
        return int(stored) if stored is not None else None

    def set_daily_goal(self, new_cards_per_day: int) -> None:
        """Save the learner's goal. Raises ValueError outside 1-100."""
        if not MIN_DAILY_GOAL <= new_cards_per_day <= MAX_DAILY_GOAL:
            raise ValueError(DAILY_GOAL_ERROR)
        self._settings.set(DAILY_GOAL_KEY, str(new_cards_per_day))

    def new_cards_per_day(self) -> int:
        """The learner's goal, or the NEW_CARDS_PER_DAY default until they choose one."""
        goal = self.daily_goal()
        return goal if goal is not None else self._default_new_cards_per_day

    def default_new_cards_per_day(self) -> int:
        return self._default_new_cards_per_day

    # ----- placement -----

    def level(self) -> tuple[int, str] | None:
        """(level, level name) from the placement quiz, or None before the learner takes or skips it."""
        level, name = self._settings.get(LEVEL_KEY), self._settings.get(LEVEL_NAME_KEY)
        return (int(level), name) if level is not None and name is not None else None

    def place_learner(self, answers: Mapping[str, str] | None, today: date) -> PlacementOutcome:
        """Score the quiz (None = skipped) and mark the material below the level as known.

        Content scores the answers and returns the ids of the easier seed sentences and their
        words. Each gets a card in the "known" state, so it comes back once for a quick check
        months later instead of being taught. Cards already reviewed are not touched.
        Skipping needs no content call: the learner starts at the first level with nothing known.
        """
        if answers is None:
            level, name, sentence_ids, word_ids = *STARTER, [], []
        else:
            result = self._content.score(answers)   # may raise ContentUnavailable: nothing saved yet
            level, name, sentence_ids, word_ids = result.level, result.level_name, result.sentence_ids, result.word_ids

        self._cards.ensure_cards([NewCard(SENTENCE_CARD, None, sentence_id) for sentence_id in sentence_ids]
                                 + [NewCard(WORD_CARD, word_id, None) for word_id in word_ids])
        known = self._cards.new_cards_for(sentence_ids, word_ids)
        self._cards.save_states({card.id: _known_state(position, today) for position, card in enumerate(known)})
        self._settings.set(LEVEL_KEY, str(level))
        self._settings.set(LEVEL_NAME_KEY, name)
        return PlacementOutcome(level, name, len(known))

    # ----- reviewing -----

    def next_card(self, today: date) -> Card | None:
        """Due reviews come first; then a new card if today's limit allows; otherwise None.

        When no new card is stored, the next sentences are pulled from content first. If content
        is down, the pull raises ContentUnavailable: without content there would be no text to show anyway.
        """
        due = self._cards.next_due(today)
        if due is not None:
            return due
        if self._new_cards_left(today) <= 0:
            return None
        new = self._cards.next_new()
        if new is None:
            self._pull()
            new = self._cards.next_new()
        return new

    def next_review(self, today: date) -> NextReview | None:
        """The next card with its text from content, its rating previews and today's numbers.

        None when there is nothing left to review today.
        """
        card = self.next_card(today)
        if card is None:
            return None
        if card.card_type == SENTENCE_CARD:
            text = self._content.sentence(card.sentence_id)
        else:
            text = self._content.word(card.word_id)
        return NextReview(card, text, self.preview_intervals(card, today), self.stats(today))

    def review(self, card_id: int, quality: int, now: datetime) -> CardState:
        """Apply a rating: compute the new state, save it, and log the review.

        Raises LookupError for an unknown card and ValueError for a quality outside 0-5.
        """
        card = self._cards.get(card_id)
        if card is None:
            raise LookupError(f"No card with id {card_id}.")
        new_state = self._strategy.next_state(card.state, quality, now.date())
        self._cards.save_state(card_id, new_state)
        self._log.add(Review(card_id, now, quality, new_state.interval_days, new_state.ease_factor))
        return new_state

    def preview_intervals(self, card: Card, today: date) -> dict[int, int]:
        """Days until the card would come back for each rating. Nothing is saved."""
        return {quality: self._strategy.next_state(card.state, quality, today).interval_days
                for quality in RATING_QUALITIES}

    def stats(self, today: date) -> ReviewStats:
        """Today's numbers, from the scheduler's own tables only (works while content is down).

        new_left_today is what is left of the daily allowance: sentences not pulled yet have no
        card here, so the scheduler cannot count them (ADR-7).
        """
        return ReviewStats(
            due_now=self._cards.count_due(today),
            new_left_today=self._new_cards_left(today),
            reviewed_today=self._log.count_reviews_on(today),
            total_cards=self._cards.count_all(),
        )

    def _new_cards_left(self, today: date) -> int:
        return max(0, self.new_cards_per_day() - self._log.count_first_reviews_on(today))

    def _pull(self) -> None:
        """Ask content for the sentences after the newest one that has a card, and add their cards."""
        feed = self._content.feed(self._cards.max_sentence_id(), PULL_SIZE)
        self._cards.ensure_cards(_cards_for(feed))


def _cards_for(feed: list[FeedItem]) -> list[NewCard]:
    """Each sentence's card followed by its word cards, so id order stays introduction order."""
    return [card for item in feed
            for card in [NewCard(SENTENCE_CARD, None, item.id), *(NewCard(WORD_CARD, w, None) for w in item.word_ids)]]


def _known_state(position: int, today: date) -> CardState:
    """A skipped card looks as if it had been answered correctly twice, and is checked again
    after KNOWN_FIRST_CHECK_DAYS plus up to KNOWN_SPREAD_DAYS, depending on its position."""
    interval = KNOWN_FIRST_CHECK_DAYS + position % KNOWN_SPREAD_DAYS
    return CardState(interval_days=interval, repetitions=2, due_date=today + timedelta(days=interval))
