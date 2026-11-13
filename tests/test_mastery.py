from datetime import UTC, datetime, timedelta

import pytest

from core.graph.space_map import SpaceMap, TopicInfo
from core.mastery import bkt
from core.mastery.fsrs import review
from core.mastery.progress import mastered_by_day
from core.mastery.select import pick_diagnostic_topic, pick_practice_topic
from core.questions.schema import QuestionType
from core.storage.learning import MasteryEvent

# sets → relational model → sql → joins;  relational model → normalization
EDGES = [("sets", "rel", 1.0), ("rel", "sql", 1.0), ("sql", "joins", 1.0), ("rel", "norm", 1.0)]


def _map() -> SpaceMap:
    names = ["sets", "rel", "sql", "joins", "norm"]
    return SpaceMap.build([TopicInfo(id=n, name=n.title(), first_seen=i) for i, n in enumerate(names)], EDGES)


def test_space_map_walks_both_ways() -> None:
    m = _map()
    assert m.ancestors("joins") == {"sql": 1, "rel": 2, "sets": 3}
    assert m.ancestors("joins", max_hops=2) == {"sql": 1, "rel": 2}
    assert m.descendants("rel") == {"sql": 1, "norm": 1, "joins": 2}


def test_posterior_matches_the_formulas() -> None:
    # P(L|correct) = .2*.9 / (.2*.9 + .8*.25)
    assert bkt.posterior(0.2, True, 0.25) == pytest.approx(0.18 / 0.38)
    # P(L|wrong) = .2*.1 / (.2*.1 + .8*.75)
    assert bkt.posterior(0.2, False, 0.25) == pytest.approx(0.02 / 0.62)


def test_update_adds_learning_and_respects_guess_rate() -> None:
    post = bkt.posterior(0.2, True, bkt.GUESS["mcq"])
    assert bkt.update(0.2, True, "mcq") == pytest.approx(post + (1 - post) * bkt.LEARN)
    assert bkt.update(0.2, True, "mcq", learn=0) == pytest.approx(post)
    # a right numeric answer is far stronger evidence than a right MCQ (guessing is unlikely)
    assert bkt.update(0.2, True, "numeric") > bkt.update(0.2, True, "mcq")


def test_repeated_correct_answers_reach_mastery_and_stay_bounded() -> None:
    p = bkt.PRIOR
    for _ in range(4):
        p = bkt.update(p, True, "short")
    assert bkt.is_mastered(p)
    for _ in range(50):
        p = bkt.update(p, True, "numeric")
    assert p <= bkt.CEILING
    for _ in range(50):
        p = bkt.update(p, False, "mcq", learn=0)
    assert p >= bkt.FLOOR


def test_correct_answer_raises_prerequisites_damped_per_hop() -> None:
    m = _map()
    p_new = bkt.update(0.2, True, "short", learn=0)
    changes = bkt.propagate(m, {}, "joins", 0.2, p_new)
    assert set(changes) == {"sql", "rel", "sets"}  # prerequisites only; not norm
    assert changes["sql"] > changes["rel"] > changes["sets"] > bkt.PRIOR
    gain = (p_new - 0.2) / 0.8
    assert changes["sql"] == pytest.approx(0.2 + 0.8 * gain * 0.5)


def test_wrong_answer_lowers_dependents() -> None:
    m = _map()
    p_new = bkt.update(0.2, False, "short", learn=0)
    changes = bkt.propagate(m, {"joins": 0.6}, "rel", 0.2, p_new)
    assert set(changes) == {"sql", "norm", "joins"}
    assert changes["joins"] < 0.6
    assert changes["sql"] < bkt.PRIOR
    assert bkt.propagate(m, {}, "rel", 0.2, 0.2) == {}


def test_diagnostic_prefers_well_connected_uncertain_topics() -> None:
    m = _map()
    first = pick_diagnostic_topic(m, {}, set())
    assert first == "rel"  # reaches every other topic
    assert pick_diagnostic_topic(m, {}, {"rel", "sets", "sql", "joins", "norm"}) is None
    # a topic we're already sure about is worth less than an uncertain one
    assert pick_diagnostic_topic(m, {"rel": 0.99}, set()) != "rel"


def test_practice_picks_weakest_ready_topic() -> None:
    m = _map()
    # nothing known: only "sets" has no prerequisites, so it's the only ready topic
    assert pick_practice_topic(m, {}) == "sets"
    # sets known: rel becomes ready; joins is weaker but its prerequisites aren't ready
    assert pick_practice_topic(m, {"sets": 0.97, "joins": 0.01}) == "rel"
    # everything mastered
    assert pick_practice_topic(m, dict.fromkeys(m.topics, 0.99)) is None
    # avoid the topic just practised when there's another option
    assert pick_practice_topic(m, {"sets": 0.97, "rel": 0.7, "norm": 0.3}, avoid={"norm"}) != "norm"


def test_mastered_by_day() -> None:
    day1 = datetime(2026, 11, 1, 10, tzinfo=UTC)
    events = [
        MasteryEvent(topic_id="a", p_known=0.96, cause="practice", ts=day1),
        MasteryEvent(topic_id="b", p_known=0.5, cause="practice", ts=day1 + timedelta(hours=1)),
        MasteryEvent(topic_id="b", p_known=0.97, cause="practice", ts=day1 + timedelta(days=1)),
        MasteryEvent(topic_id="a", p_known=0.6, cause="practice", ts=day1 + timedelta(days=2)),
    ]
    assert mastered_by_day(events) == [
        {"date": "2026-11-01", "mastered": 1},
        {"date": "2026-11-02", "mastered": 2},
        {"date": "2026-11-03", "mastered": 1},
    ]


def test_fsrs_schedules_further_out_for_easier_ratings() -> None:
    at = datetime(2026, 11, 1, tzinfo=UTC)
    _, again = review(None, "again", at)
    state, easy = review(None, "easy", at)
    assert at <= again < easy
    _, later = review(state, "good", easy)
    assert later > easy


def test_ability_corrects_for_guessing() -> None:
    assert bkt.ability([]) == bkt.PRIOR
    # all wrong → the floor; all right → near the ceiling
    assert bkt.ability([("mcq", False)] * 5) == 0.05
    assert bkt.ability([("short", True)] * 5) == 0.95
    # 25% right on MCQs is what guessing alone gives: no evidence of knowing anything
    guessing: list[tuple[QuestionType, bool]] = [("mcq", True), ("mcq", False), ("mcq", False), ("mcq", False)]
    assert bkt.ability(guessing) == 0.05


def test_unassessed_estimates_follow_prerequisites() -> None:
    m = _map()
    est = bkt.estimate_unassessed(m, {"rel": 0.95}, 0.8)
    assert "rel" not in est  # assessed topics are left alone
    assert est["sets"] == pytest.approx(0.8)  # no prerequisites
    assert est["sql"] > est["joins"]  # joins needs sql, which is itself uncertain
    weak = bkt.estimate_unassessed(m, {"rel": 0.05}, 0.8)
    assert weak["sql"] < est["sql"]  # a weak prerequisite drags its dependents down


def test_simulation_meets_the_diagnostic_target() -> None:
    from core.mastery.simulate import simulate

    r = simulate(learners=40, seed=1)
    assert r.diagnostic_accuracy >= 0.70
    assert r.diagnostic_accuracy > r.baseline_all_unknown
    assert 0.5 < r.auc < r.oracle_auc <= 1.0
