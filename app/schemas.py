from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


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
    week_id: str
    quiz_ids: List[int]
    quizzes: List[QuizDefinitionResponse]


class GetQuizRequest(BaseModel):
    quiz_ids: List[int] = []


# Admin schemas
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class AdminQuizUpdateRequest(BaseModel):
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    hint: Optional[str] = None