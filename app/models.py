from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True)
    url = Column(String(500))
    questions = Column(Text)  # JSON string
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    

class QuizDefinition(Base):
    __tablename__ = "quiz_definition"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    title = Column(String(255), index=True)
    week_id = Column(String(100), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())