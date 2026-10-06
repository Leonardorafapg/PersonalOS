"""Import every model so Base.metadata is complete (used by Alembic and tests),
and register each entity type with the audit/undo machinery."""

from app.core.db import Base  # noqa: F401
from app.domains.audit.models import OperationLog  # noqa: F401
from app.domains.audit.service import MODELS
from app.domains.calendar.models import CalendarEntry
from app.domains.identity.models import User, UserPreferences  # noqa: F401
from app.domains.planning.models import DailyPlan
from app.domains.projects.models import Project
from app.domains.routines.models import Routine, WorkoutSession
from app.domains.study.models import StudySession, StudyTopic
from app.domains.tasks.models import Task

MODELS.update(
    {
        "task": Task,
        "calendar_entry": CalendarEntry,
        "project": Project,
        "study_topic": StudyTopic,
        "study_session": StudySession,
        "routine": Routine,
        "workout_session": WorkoutSession,
        "daily_plan": DailyPlan,
        "preferences": UserPreferences,
    }
)
