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


# User quiz result schemas
class QuizAnswerSubmit(BaseModel):
    """Single answer submitted by user."""
    quiz_id: int
    question_index: int
    selected_answer: str


class QuizResultSubmit(BaseModel):
    """User's quiz result submission."""
    week_id: str
    answers: List[QuizAnswerSubmit]


class QuizResultResponse(BaseModel):
    """Response after submitting quiz results."""
    id: int
    user_id: str
    week_id: str
    score: int
    total_questions: int
    percentage: float
    attempt_number: int
    is_best: bool
    is_new_best: bool  # True if this attempt is better than previous best
    completed_at: datetime
    
    class Config:
        from_attributes = True


class UserWeekResultSummary(BaseModel):
    """Summary of user's results for a specific week."""
    week_id: str
    best_score: int
    best_percentage: float
    total_attempts: int
    last_attempt_at: datetime
    best_attempt_number: int


class UserResultHistory(BaseModel):
    """User's quiz result history."""
    user_id: str
    total_weeks_attempted: int
    results_by_week: List[UserWeekResultSummary]