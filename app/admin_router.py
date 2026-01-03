from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Quiz, QuizDefinition
from app.schemas import (
    AdminLoginRequest, AdminLoginResponse, QuizDefinitionResponse,
    QuizQuestion, AdminQuizUpdateRequest
)
from app.auth import authenticate_admin, create_access_token, verify_admin
from app.logging_config import get_logger
import json
from typing import List

logger = get_logger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.post("/login", response_model=AdminLoginResponse)
def admin_login(credentials: AdminLoginRequest):
    """Admin login endpoint."""
    if not authenticate_admin(credentials.username, credentials.password):
        logger.warning(f"Failed admin login attempt for username: {credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": credentials.username, "role": "admin"},
        expires_delta=timedelta(hours=8)
    )
    
    logger.info(f"Admin {credentials.username} logged in successfully")
    return AdminLoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=28800  # 8 hours in seconds
    )


@admin_router.get("/weeks/{week_id}/questions")
def get_all_week_questions(
    week_id: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin)
):
    """Get ALL questions for a specific week (no limit for admin)."""
    logger.info(f"Admin fetching all questions for week: {week_id}")
    
    # Get all quiz definitions for this week
    quiz_defs = db.query(QuizDefinition).filter(
        QuizDefinition.week_id == week_id
    ).all()
    
    if not quiz_defs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quizzes found for week {week_id}"
        )
    
    # Get all quizzes
    quiz_ids = [qd.quiz_id for qd in quiz_defs]
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    
    # Collect all questions
    all_questions = []
    for quiz in quizzes:
        questions_data = json.loads(quiz.questions)
        for q in questions_data:
            all_questions.append({
                "quiz_id": quiz.id,
                "quiz_title": quiz.title,
                **q
            })
    
    logger.info(f"Retrieved {len(all_questions)} total questions for week {week_id}")
    return {
        "week_id": week_id,
        "total_questions": len(all_questions),
        "questions": all_questions
    }


@admin_router.get("/weeks/{week_id}/stats")
def get_week_stats(
    week_id: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin)
):
    """Get statistics for a specific week."""
    quiz_defs = db.query(QuizDefinition).filter(
        QuizDefinition.week_id == week_id
    ).all()
    
    if not quiz_defs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quizzes found for week {week_id}"
        )
    
    quiz_ids = [qd.quiz_id for qd in quiz_defs]
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    
    total_questions = sum(len(json.loads(q.questions)) for q in quizzes)
    
    return {
        "week_id": week_id,
        "total_quizzes": len(quizzes),
        "total_questions": total_questions,
        "can_delete_more": total_questions > 100
    }


@admin_router.delete("/quizzes/{quiz_id}")
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin)
):
    """Delete an entire quiz and its definition."""
    # Get the quiz
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    # Get quiz definition to check week
    quiz_def = db.query(QuizDefinition).filter(
        QuizDefinition.quiz_id == quiz_id
    ).first()
    
    if quiz_def:
        week_id = quiz_def.week_id
        
        # Check minimum questions constraint
        other_quiz_defs = db.query(QuizDefinition).filter(
            QuizDefinition.week_id == week_id,
            QuizDefinition.quiz_id != quiz_id
        ).all()
        
        other_quiz_ids = [qd.quiz_id for qd in other_quiz_defs]
        other_quizzes = db.query(Quiz).filter(Quiz.id.in_(other_quiz_ids)).all()
        
        remaining_questions = sum(len(json.loads(q.questions)) for q in other_quizzes)
        questions_in_this_quiz = len(json.loads(quiz.questions))
        
        if remaining_questions < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete quiz. Week must have at least 100 questions. "
                       f"Currently {remaining_questions + questions_in_this_quiz} questions, "
                       f"would have {remaining_questions} after deletion."
            )
        
        # Delete quiz definition
        db.delete(quiz_def)
    
    # Delete quiz
    db.delete(quiz)
    db.commit()
    
    logger.info(f"Admin deleted quiz {quiz_id}")
    return {
        "message": f"Quiz {quiz_id} deleted successfully",
        "deleted_quiz_id": quiz_id
    }


@admin_router.delete("/quizzes/{quiz_id}/questions/{question_index}")
def delete_question(
    quiz_id: int,
    question_index: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin)
):
    """Delete a specific question from a quiz."""
    # Get the quiz
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    # Get quiz definition to check week
    quiz_def = db.query(QuizDefinition).filter(
        QuizDefinition.quiz_id == quiz_id
    ).first()
    
    if not quiz_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz definition not found for quiz {quiz_id}"
        )
    
    week_id = quiz_def.week_id
    
    # Calculate total questions in the week
    all_quiz_defs = db.query(QuizDefinition).filter(
        QuizDefinition.week_id == week_id
    ).all()
    
    quiz_ids = [qd.quiz_id for qd in all_quiz_defs]
    all_quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    
    total_questions = sum(len(json.loads(q.questions)) for q in all_quizzes)
    
    if total_questions <= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete question. Week must have at least 100 questions. "
                   f"Currently has exactly {total_questions} questions."
        )
    
    # Delete the question
    questions = json.loads(quiz.questions)
    
    if question_index < 0 or question_index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question index {question_index} not found. Quiz has {len(questions)} questions."
        )
    
    deleted_question = questions.pop(question_index)
    quiz.questions = json.dumps(questions)
    db.commit()
    
    logger.info(f"Admin deleted question {question_index} from quiz {quiz_id}")
    return {
        "message": "Question deleted successfully",
        "deleted_question": deleted_question,
        "remaining_questions": len(questions),
        "week_total_questions": total_questions - 1
    }


@admin_router.put("/quizzes/{quiz_id}/questions/{question_index}")
def update_question(
    quiz_id: int,
    question_index: int,
    update_data: AdminQuizUpdateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin)
):
    """Update a specific question in a quiz."""
    # Get the quiz
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    # Update the question
    questions = json.loads(quiz.questions)
    
    if question_index < 0 or question_index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question index {question_index} not found. Quiz has {len(questions)} questions."
        )
    
    # Update only provided fields
    if update_data.question is not None:
        questions[question_index]["question"] = update_data.question
    if update_data.options is not None:
        questions[question_index]["options"] = update_data.options
    if update_data.correct_answer is not None:
        questions[question_index]["correct_answer"] = update_data.correct_answer
    if update_data.hint is not None:
        questions[question_index]["hint"] = update_data.hint
    
    quiz.questions = json.dumps(questions)
    db.commit()
    
    logger.info(f"Admin updated question {question_index} in quiz {quiz_id}")
    return {
        "message": "Question updated successfully",
        "updated_question": questions[question_index]
    }


@admin_router.get("/quizzes")
def list_all_quizzes(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: dict = Depends(verify_admin)
):
    """List all quizzes with pagination."""
    total = db.query(func.count(Quiz.id)).scalar()
    quizzes = db.query(Quiz).offset(skip).limit(limit).all()
    
    quiz_list = []
    for quiz in quizzes:
        quiz_def = db.query(QuizDefinition).filter(
            QuizDefinition.quiz_id == quiz.id
        ).first()
        
        questions_count = len(json.loads(quiz.questions))
        
        quiz_list.append({
            "id": quiz.id,
            "title": quiz.title,
            "url": quiz.url,
            "questions_count": questions_count,
            "week_id": quiz_def.week_id if quiz_def else None,
            "created_at": quiz.created_at
        })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "quizzes": quiz_list
    }
