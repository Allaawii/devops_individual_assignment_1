"""ReviewService: the single entry point (Facade) into the scheduler domain.

It is also the Observer listener: create_app() subscribes on_sentence_added to
ContentService, so every new sentence gets its cards without content importing this module.
"""

from datetime import date, datetime

from trainer.scheduler.algorithms import AGAIN, EASY, GOOD, HARD, SchedulingStrategy
from trainer.scheduler.models import Card, CardState, Review, ReviewStats
from trainer.scheduler.repository import CardRepository, ReviewLog, SettingsStore

DAILY_GOAL_KEY = "new_cards_per_day"
MIN_DAILY_GOAL = 1
MAX_DAILY_GOAL = 100


class ReviewService:
    def __init__(self, card_repo: CardRepository, review_log: ReviewLog, settings: SettingsStore,
                 strategy: SchedulingStrategy, default_new_cards_per_day: int) -> None:
        self._cards = card_repo
        self._log = review_log
        self._settings = settings
        self._strategy = strategy
        self._default_new_cards_per_day = default_new_cards_per_day

    # ----- daily goal -----

    def daily_goal(self) -> int | None:
        """The number of new cards a day the learner chose, or None before they choose."""
        stored = self._settings.get(DAILY_GOAL_KEY)
        return int(stored) if stored is not None else None

    def set_daily_goal(self, new_cards_per_day: int) -> None:
        """Save the learner's goal. Raises ValueError outside 1-100."""
        if not MIN_DAILY_GOAL <= new_cards_per_day <= MAX_DAILY_GOAL:
            raise ValueError(f"Choose between {MIN_DAILY_GOAL} and {MAX_DAILY_GOAL} new cards a day.")
        self._settings.set(DAILY_GOAL_KEY, str(new_cards_per_day))

    def new_cards_per_day(self) -> int:
        """The learner's goal, or the NEW_CARDS_PER_DAY default until they choose one."""
        goal = self.daily_goal()
        return goal if goal is not None else self._default_new_cards_per_day

    # ----- observer -----

    def on_sentence_added(self, sentence_id: int, word_ids: list[int]) -> None:
        """Observer callback: one card for the sentence, then one for each word that has none yet."""
        self._cards.ensure_sentence_card(sentence_id)
        self._cards.ensure_word_cards(word_ids)

    # ----- reviewing -----

    def next_card(self, today: date) -> Card | None:
        """Due reviews come first; then a new card if today's limit allows; otherwise None."""
        due = self._cards.next_due(today)
        if due is not None:
            return due
        if self._new_cards_left(today) > 0:
            return self._cards.next_new()
        return None

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
                for quality in (AGAIN, HARD, GOOD, EASY)}

    def stats(self, today: date) -> ReviewStats:
        return ReviewStats(
            due_now=self._cards.count_due(today),
            new_left_today=min(self._cards.count_new(), self._new_cards_left(today)),
            reviewed_today=self._log.count_reviews_on(today),
            total_cards=self._cards.count_all(),
        )

    def _new_cards_left(self, today: date) -> int:
        return max(0, self.new_cards_per_day() - self._log.count_first_reviews_on(today))
