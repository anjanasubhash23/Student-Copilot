"""Simulated learners, to evaluate the diagnostic and the mastery model without real students (spec section 11).

Each learner has a hidden true state: which topics they know. Knowledge respects the graph: a topic whose
prerequisites aren't all known is rarely known itself. Answers follow the same slip and guess rates BKT
assumes, and practice teaches with the same learn rate, so this measures how well the *procedures*
(question choice, propagation, BKT updates) recover the truth when the model's assumptions hold. Real
learners will fit those assumptions less well; treat these numbers as an upper bound.

Two measures, with targets from the spec:
- Diagnostic accuracy: after the 10-question diagnostic, the share of topics whose known/unknown call
  (p_known >= 0.5) matches the truth. Target >= 0.70. Reported next to baselines: predicting "unknown" for
  everything, the diagnostic without propagation, and without the post-diagnostic estimates.
- Mastery-model AUC: during practice, how well P(correct) predicted from p_known ranks right answers above
  wrong ones. Target >= 0.75.
"""

import random
from dataclasses import dataclass, field
from statistics import mean

from core.graph.space_map import SpaceMap, TopicInfo
from core.ingest.schema import SpaceGraph
from core.mastery import bkt
from core.mastery.select import pick_diagnostic_topic, pick_practice_topic
from core.questions.schema import QuestionType

QUESTION_MIX: list[tuple[QuestionType, float]] = [("mcq", 0.45), ("msq", 0.15), ("short", 0.3), ("numeric", 0.1)]
DIAGNOSTIC_QUESTIONS = 10
KNOWN = 0.5  # p_known at or above this is a "known" call


@dataclass
class Learner:
    known: dict[str, bool]


@dataclass
class SimulationResult:
    learners: int
    topics: float  # mean topics per map
    known_share: float  # mean share of topics truly known before practice
    diagnostic_accuracy: float
    diagnostic_balanced_accuracy: float
    baseline_all_unknown: float
    without_propagation: float
    without_estimates: float  # propagation only: the flat prior for topics the diagnostic didn't reach
    auc: float
    oracle_auc: float  # AUC if predictions came from the learner's true (hidden) state: an unreachable ceiling
    answers: int  # practice answers the AUC is computed over
    per_learner: list[float] = field(default_factory=list)


# Maps


def random_map(n_topics: int, rng: random.Random) -> SpaceMap:
    """A course-like DAG: topics in teaching order, each with 0-3 prerequisites, mostly among recent topics."""
    topics = [TopicInfo(id=f"t{i}", name=f"Topic {i}", first_seen=i) for i in range(n_topics)]
    edges: list[tuple[str, str, float]] = []
    for i in range(1, n_topics):
        k = rng.choices([0, 1, 2, 3], weights=[0.2, 0.4, 0.3, 0.1])[0]
        window = list(range(max(0, i - 8), i))
        for j in rng.sample(window, min(k, len(window))):
            edges.append((f"t{j}", f"t{i}", 1.0))
    return SpaceMap.build(topics, edges)


def map_from_graph(graph: SpaceGraph) -> SpaceMap:
    """The SpaceMap of an ingested graph JSON (data/cache/<space>.graph.json), to simulate on real structure."""
    ids = {t.name: f"t{i}" for i, t in enumerate(graph.topics)}
    topics = [TopicInfo(id=ids[t.name], name=t.name, first_seen=t.first_seen) for t in graph.topics]
    edges = [
        (ids[p.requires], ids[p.topic], p.confidence) for p in graph.prereqs if p.topic in ids and p.requires in ids
    ]
    return SpaceMap.build(topics, edges)


# Learners


def sample_learner(space: SpaceMap, rng: random.Random) -> Learner:
    """Knows each topic with their ability if they know its prerequisites, and rarely otherwise."""
    ability = rng.uniform(0.15, 0.9)
    known: dict[str, bool] = {}
    for t in sorted(space.topics.values(), key=lambda t: t.first_seen):
        ready = all(known.get(p, False) for p in space.prereqs.get(t.id, ()))
        known[t.id] = rng.random() < (ability if ready else ability * 0.15)
    return Learner(known=known)


def _qtype(rng: random.Random) -> QuestionType:
    return rng.choices([q for q, _ in QUESTION_MIX], weights=[w for _, w in QUESTION_MIX])[0]


def answer(learner: Learner, topic: str, qtype: QuestionType, rng: random.Random) -> bool:
    if learner.known[topic]:
        return rng.random() >= bkt.SLIP
    return rng.random() < bkt.GUESS[qtype]


# The diagnostic


def run_diagnostic(
    space: SpaceMap,
    learner: Learner,
    rng: random.Random,
    propagate: bool = True,
    estimate: bool = True,
    questions: int = DIAGNOSTIC_QUESTIONS,
) -> dict[str, float]:
    """The real topic choice and BKT updates, then (with `estimate`) the starting estimates for the topics it
    didn't reach, as the app does. Returns p_known per topic."""
    mastery: dict[str, float] = {}
    asked: set[str] = set()
    answers: list[tuple[QuestionType, bool]] = []
    for _ in range(min(questions, len(space.topics))):
        topic = pick_diagnostic_topic(space, mastery, asked)
        if topic is None:
            break
        asked.add(topic)
        qtype = _qtype(rng)
        correct = answer(learner, topic, qtype, rng)
        answers.append((qtype, correct))
        p_old = mastery.get(topic, bkt.PRIOR)
        p_new = bkt.update(p_old, correct, qtype, learn=0.0)
        if propagate:
            mastery.update(bkt.propagate(space, mastery, topic, p_old, p_new))
        mastery[topic] = p_new
    if estimate:
        mastery.update(bkt.estimate_unassessed(space, mastery, bkt.ability(answers)))
    return mastery


def accuracy(space: SpaceMap, learner: Learner, mastery: dict[str, float]) -> tuple[float, float]:
    """(accuracy, balanced accuracy) of the known/unknown calls against the truth."""
    calls = [(mastery.get(t, bkt.PRIOR) >= KNOWN, learner.known[t]) for t in space.topics]
    acc = mean(pred == truth for pred, truth in calls)
    pos = [pred for pred, truth in calls if truth]
    neg = [not pred for pred, truth in calls if not truth]
    recalls = [mean(group) for group in (pos, neg) if group]
    return acc, mean(recalls)


# Practice, for the AUC


def run_practice(
    space: SpaceMap, learner: Learner, mastery: dict[str, float], steps: int, rng: random.Random
) -> list[tuple[float, float, bool]]:
    """Practice as the app does it; the learner really learns (rate LEARN).

    Returns (model's predicted P(correct), the same from the true hidden state, correct) per answer."""
    mastery = dict(mastery)
    known = dict(learner.known)
    pairs: list[tuple[float, float, bool]] = []
    last: str | None = None
    for _ in range(steps):
        topic = pick_practice_topic(space, mastery, {last} if last else None)
        if topic is None:
            break
        qtype = _qtype(rng)
        p = mastery.get(topic, bkt.PRIOR)
        predicted = p * (1 - bkt.SLIP) + (1 - p) * bkt.GUESS[qtype]
        oracle = (1 - bkt.SLIP) if known[topic] else bkt.GUESS[qtype]
        correct = answer(Learner(known), topic, qtype, rng)
        pairs.append((predicted, oracle, correct))
        mastery[topic] = bkt.update(p, correct, qtype)
        if not known[topic] and rng.random() < bkt.LEARN:
            known[topic] = True
        last = topic
    return pairs


def auc(pairs: list[tuple[float, bool]]) -> float:
    """Probability a random right answer was predicted higher than a random wrong one (ties count half)."""
    ranked = sorted(pairs, key=lambda x: x[0])
    n_pos = sum(c for _, c in pairs)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = 0.0
    i = 0
    while i < len(ranked):  # average ranks over ties
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        rank_sum += avg_rank * sum(c for _, c in ranked[i:j])
        i = j
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


# Putting it together


def simulate(
    learners: int = 200,
    seed: int = 7,
    graph: SpaceGraph | None = None,
    topics: tuple[int, int] = (40, 80),
    practice_steps: int = 40,
) -> SimulationResult:
    rng = random.Random(seed)
    fixed = map_from_graph(graph) if graph else None
    accs, bals, base, noprop, noest, sizes, known_shares = [], [], [], [], [], [], []
    pairs: list[tuple[float, float, bool]] = []
    for _ in range(learners):
        space = fixed or random_map(rng.randint(*topics), rng)
        learner = sample_learner(space, rng)
        sizes.append(len(space.topics))
        known_shares.append(mean(learner.known.values()))
        # Same answers for the with- and without-propagation runs: replay from one seed.
        sub_seed = rng.random()
        mastery = run_diagnostic(space, learner, random.Random(sub_seed))
        acc, bal = accuracy(space, learner, mastery)
        accs.append(acc)
        bals.append(bal)
        noprop.append(
            accuracy(space, learner, run_diagnostic(space, learner, random.Random(sub_seed), propagate=False))[0]
        )
        noest.append(
            accuracy(space, learner, run_diagnostic(space, learner, random.Random(sub_seed), estimate=False))[0]
        )
        base.append(accuracy(space, learner, {})[0])
        pairs.extend(run_practice(space, learner, mastery, practice_steps, rng))
    return SimulationResult(
        learners=learners,
        topics=mean(sizes),
        known_share=mean(known_shares),
        diagnostic_accuracy=mean(accs),
        diagnostic_balanced_accuracy=mean(bals),
        baseline_all_unknown=mean(base),
        without_propagation=mean(noprop),
        without_estimates=mean(noest),
        auc=auc([(p, c) for p, _, c in pairs]),
        oracle_auc=auc([(o, c) for _, o, c in pairs]),
        answers=len(pairs),
        per_learner=accs,
    )
