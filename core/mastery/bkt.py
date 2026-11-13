"""Bayesian Knowledge Tracing (spec section 6), by hand so the logic is visible.

P(L | correct) = P(L)(1 - S) / [P(L)(1 - S) + (1 - P(L)) G]
P(L | wrong)   = P(L) S      / [P(L) S      + (1 - P(L)) (1 - G)]
P(L_next)      = P(L | obs) + (1 - P(L | obs)) T
"""

from core.graph.space_map import SpaceMap
from core.questions.schema import QuestionType

PRIOR = 0.20  # P(L0), before any evidence
LEARN = 0.15  # T: chance of learning the topic during one practice step
SLIP = 0.10  # S: knows it, answers wrong
GUESS: dict[QuestionType, float] = {"mcq": 0.25, "msq": 0.05, "short": 0.05, "numeric": 0.01}  # G
MASTERED = 0.95

DAMPING = 0.5  # diagnostic propagation: effect halves with each hop
PROPAGATION_HOPS = 3

# Keep p_known strictly inside (0, 1): at exactly 0 or 1 no evidence could ever move it again.
FLOOR, CEILING = 0.001, 0.999


def _clamp(p: float) -> float:
    return min(max(p, FLOOR), CEILING)


def posterior(p: float, correct: bool, guess: float, slip: float = SLIP) -> float:
    if correct:
        known, unknown = p * (1 - slip), (1 - p) * guess
    else:
        known, unknown = p * slip, (1 - p) * (1 - guess)
    return known / (known + unknown)


def update(p: float, correct: bool, qtype: QuestionType, learn: float = LEARN) -> float:
    """p_known after one answer. The diagnostic passes learn=0: it measures, it doesn't teach."""
    post = posterior(p, correct, GUESS[qtype])
    return _clamp(post + (1 - post) * learn)


def propagate(
    space: SpaceMap, mastery: dict[str, float], topic_id: str, p_old: float, p_new: float
) -> dict[str, float]:
    """Diagnostic only: spread an answer's evidence to related topics.

    Knowing a topic is evidence of knowing its prerequisites, so a rise moves each prerequisite the same
    fraction of the way to 1, damped by DAMPING per hop. Not knowing a topic is evidence against the topics
    built on it, so a fall moves each dependent the same fraction of the way to 0, damped the same way.
    Returns the new values of the topics that changed.
    """
    changes: dict[str, float] = {}
    if p_new > p_old:
        gain = (p_new - p_old) / (1 - p_old)
        for other, hops in space.ancestors(topic_id, PROPAGATION_HOPS).items():
            p = mastery.get(other, PRIOR)
            changes[other] = _clamp(p + (1 - p) * gain * DAMPING**hops)
    elif p_new < p_old:
        loss = (p_old - p_new) / p_old
        for other, hops in space.descendants(topic_id, PROPAGATION_HOPS).items():
            p = mastery.get(other, PRIOR)
            changes[other] = _clamp(p * (1 - loss * DAMPING**hops))
    return changes


def is_mastered(p: float) -> bool:
    return p >= MASTERED


# After the diagnostic: replace the flat prior for topics it didn't ask about (spec: P(L0) "overwritten by
# the diagnostic"). A strong learner and a weak one shouldn't start from the same 0.20 everywhere.

UNMET_PREREQS = 0.25  # relative chance of knowing a topic whose prerequisites you don't know


def ability(answers: list[tuple[QuestionType, bool]]) -> float:
    """The share of topics a learner knows, from their answers, corrected for guessing and slips.

    With c the share answered right and g the mean guess rate: c = a(1 - S) + (1 - a)g, so a = (c - g) / (1 - S - g).
    """
    if not answers:
        return PRIOR
    c = sum(correct for _, correct in answers) / len(answers)
    g = sum(GUESS[q] for q, _ in answers) / len(answers)
    return min(max((c - g) / (1 - SLIP - g), 0.05), 0.95)


def estimate_unassessed(space: SpaceMap, mastery: dict[str, float], learner_ability: float) -> dict[str, float]:
    """Starting p_known for every topic the diagnostic didn't reach: the learner's ability, discounted by how
    likely they are to know its prerequisites. Topics are taken in teaching order so estimates build on each other."""
    estimates: dict[str, float] = {}

    def known(topic: str) -> float:
        return mastery.get(topic, estimates.get(topic, learner_ability))

    for topic in sorted(space.topics.values(), key=lambda t: (t.first_seen, t.id)):
        if topic.id in mastery:
            continue
        ready = 1.0
        for pre in space.prereqs.get(topic.id, ()):
            ready *= known(pre)
        estimates[topic.id] = _clamp(learner_ability * (ready + UNMET_PREREQS * (1 - ready)))
    return estimates
