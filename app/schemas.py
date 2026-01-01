from datetime import datetime
from pydantic import BaseModel
from typing import List


class QuizRequest(BaseModel):
    url: str


class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    hint: str


class QuizResponse(BaseModel):
    title: str
    questions: List[QuizQuestion]
    

class QuizDefinitionResponse(BaseModel):
    id: int
    quiz_id: int
    title: str
    week_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class WeeklyQuizGroup(BaseModel):
    week_label: str
    quiz_ids: List[int]
    quizzes: List[QuizDefinitionResponse]


class GetQuizRequest(BaseModel):
    quiz_ids: List[int] = []