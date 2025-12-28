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

    class Config:
        from_attributes = True
