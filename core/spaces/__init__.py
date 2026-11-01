"""Study spaces: a learner's container for the courses and material they're studying."""

from core.spaces.models import StudySpace
from core.spaces.repository import AlreadyExistsError, StudySpaceRepository

__all__ = ["AlreadyExistsError", "StudySpace", "StudySpaceRepository"]
