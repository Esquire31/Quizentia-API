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
    selected_questions: Optional[List[int]] = None
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


class QuestionSelectionUpdate(BaseModel):
    """Update question selection for a quiz in a week."""
    quiz_definition_id: int
    selected_indices: List[int]


class BulkQuestionSelectionUpdate(BaseModel):
    """Update question selections for multiple quizzes in a week."""
    selections: List[QuestionSelectionUpdate]


class WeeklyQuestionsResponse(BaseModel):
    """Response for weekly questions."""
    week_id: str
    total_questions: int
    questions: List[dict]