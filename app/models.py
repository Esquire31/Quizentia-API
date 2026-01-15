from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base

class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True)
    url = Column(String(500), unique=True)  # URL should be unique
    questions = Column(Text)  # JSON array: [{question, options, correct_answer, hint}, ...]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    

class WeekQuestions(Base):
    """Tracks which questions from a quiz are selected/unselected for each week."""
    __tablename__ = "week_questions"

    id = Column(Integer, primary_key=True, index=True)
    week_id = Column(String(100), index=True, nullable=False)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    selected_indices = Column(Text, nullable=False)  # JSON array: [0, 2, 3, 5, ...]
    unselected_indices = Column(Text, nullable=False)  # JSON array: [1, 4, 6, 7, ...]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('week_id', 'quiz_id', name='uq_week_quiz'),
    )


class BackupQuestions(Base):
    """Questions not used in ANY week (neither selected nor unselected).
    One row per quiz with all unused question indices."""
    __tablename__ = "backup_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False, unique=True)
    question_indices = Column(Text, nullable=False)  # JSON array: [1, 2, 3, 4, ...]
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WeekSummary(Base):
    """Summary of question counts for each week for fast validation."""
    __tablename__ = "week_summary"

    week_id = Column(String(100), primary_key=True)
    total_selected = Column(Integer, nullable=False, default=0)
    total_unselected = Column(Integer, nullable=False, default=0)
    total_quizzes = Column(Integer, nullable=False, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# Legacy model - to be deprecated after migration
class QuizDefinition(Base):
    __tablename__ = "quiz_definition"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    title = Column(String(255), index=True)
    week_id = Column(String(100), index=True)
    selected_questions = Column(Text, nullable=True)  # JSON array of selected indices
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Legacy model - to be deprecated after migration
class BackupQuestion(Base):
    """LEGACY: Stores individual backup questions. Being replaced by BackupQuestions."""
    __tablename__ = "backup_questions_old"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    question_index = Column(Integer, nullable=False)
    week_id = Column(String(100), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())