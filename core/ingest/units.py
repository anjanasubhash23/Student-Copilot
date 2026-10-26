from core.ingest.schema import Topic, Unit, UnitsOut
from core.llm import load_prompt, structured


def group_units(topics: list[Topic]) -> list[Unit]:
    """Ask the LLM to group topics into ordered units; anything it drops goes into 'Other'."""
    by_position = sorted(topics, key=lambda t: min(t.pages, default=0))
    listing = "\n".join(f"- {t.name}: {t.summary}" for t in by_position)
    out = structured(load_prompt("units", topics=listing), UnitsOut)

    known = {t.name for t in topics}
    seen: set[str] = set()
    units: list[Unit] = []
    for draft in out.units:
        names = [n for n in draft.topics if n in known and n not in seen]
        seen.update(names)
        if names:
            units.append(Unit(name=draft.name, order=len(units) + 1, topics=names))

    leftover = [t.name for t in by_position if t.name not in seen]
    if leftover:
        units.append(Unit(name="Other", order=len(units) + 1, topics=leftover))
    return units
