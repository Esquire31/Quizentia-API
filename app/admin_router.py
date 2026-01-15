from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Quiz, WeekQuestions, BackupQuestions, WeekSummary
from app.schemas import (
    QuizDefinitionResponse,
    QuizQuestion, AdminQuizUpdateRequest, BulkQuestionSelectionUpdate
)
from app.firebase_auth import require_admin
from app.logging_config import get_logger
from app.ingestion_helpers import update_week_summary
import json
from typing import List

logger = get_logger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("/weeks/{week_id}/questions")
def get_all_week_questions(
    week_id: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Get ALL questions (selected + unselected) for a specific week."""
    logger.info(f"Admin fetching all questions for week: {week_id}")
    
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.week_id == week_id
    ).all()
    
    if not week_qs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quizzes found for week {week_id}"
        )
    
    quiz_ids = [wq.quiz_id for wq in week_qs]
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    quiz_map = {q.id: q for q in quizzes}
    
    all_questions = []
    for wq in week_qs:
        quiz = quiz_map.get(wq.quiz_id)
        if not quiz:
            continue
        
        questions_data = json.loads(quiz.questions)
        for idx, q in enumerate(questions_data):
            all_questions.append({
                "quiz_id": quiz.id,
                "quiz_title": quiz.title,
                "question_index": idx,
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
    admin: dict = Depends(require_admin)
):
    """Get statistics for a specific week."""
    summary = db.query(WeekSummary).filter(
        WeekSummary.week_id == week_id
    ).first()
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for week {week_id}"
        )
    
    return {
        "week_id": week_id,
        "total_quizzes": summary.total_quizzes,
        "total_selected": summary.total_selected,
        "total_unselected": summary.total_unselected,
        "total_questions": summary.total_selected + summary.total_unselected,
        "can_delete_more": summary.total_selected > 100
    }


@admin_router.delete("/quizzes/{quiz_id}")
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Delete an entire quiz. WARNING: This removes it from ALL weeks."""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    # Check if quiz is used in any week
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.quiz_id == quiz_id
    ).all()
    
    if week_qs:
        # Quiz is used in weeks - need to check if we can delete
        weeks_affected = [wq.week_id for wq in week_qs]
        logger.warning(f"Quiz {quiz_id} is used in weeks: {weeks_affected}")
        
        # For now, prevent deletion if used in any week
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete quiz. It is used in weeks: {weeks_affected}. "
                   "Remove it from weeks first using question selection API."
        )
    
    # Delete from backup if exists
    backup = db.query(BackupQuestions).filter(
        BackupQuestions.quiz_id == quiz_id
    ).first()
    if backup:
        db.delete(backup)
    
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
    admin: dict = Depends(require_admin)
):
    """Delete a specific question from a quiz. This affects the quiz globally."""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    questions = json.loads(quiz.questions)
    
    if question_index < 0 or question_index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question index {question_index} not found. Quiz has {len(questions)} questions."
        )
    
    deleted_question = questions.pop(question_index)
    quiz.questions = json.dumps(questions)
    
    # Update all WeekQuestions entries that reference this quiz
    # Need to adjust indices for questions after the deleted one
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.quiz_id == quiz_id
    ).all()
    
    for wq in week_qs:
        selected = json.loads(wq.selected_indices)
        unselected = json.loads(wq.unselected_indices)
        
        # Remove the deleted index
        selected = [i for i in selected if i != question_index]
        unselected = [i for i in unselected if i != question_index]
        
        # Adjust indices > question_index (shift down by 1)
        selected = [i - 1 if i > question_index else i for i in selected]
        unselected = [i - 1 if i > question_index else i for i in unselected]
        
        wq.selected_indices = json.dumps(selected)
        wq.unselected_indices = json.dumps(unselected)
    
    # Update backup if exists
    backup = db.query(BackupQuestions).filter(
        BackupQuestions.quiz_id == quiz_id
    ).first()
    
    if backup:
        indices = json.loads(backup.question_indices)
        indices = [i for i in indices if i != question_index]
        indices = [i - 1 if i > question_index else i for i in indices]
        
        if indices:
            backup.question_indices = json.dumps(indices)
        else:
            db.delete(backup)
    
    db.commit()
    
    logger.info(f"Admin deleted question {question_index} from quiz {quiz_id}")
    return {
        "message": "Question deleted successfully and all references updated",
        "deleted_question": deleted_question,
        "remaining_questions": len(questions)
    }


@admin_router.put("/quizzes/{quiz_id}/questions/{question_index}")
def update_question(
    quiz_id: int,
    question_index: int,
    update_data: AdminQuizUpdateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Update a specific question in a quiz."""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
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
    admin: dict = Depends(require_admin)
):
    """List all quizzes with pagination."""
    total = db.query(func.count(Quiz.id)).scalar()
    quizzes = db.query(Quiz).offset(skip).limit(limit).all()
    
    quiz_list = []
    for quiz in quizzes:
        # Check which weeks use this quiz
        week_qs = db.query(WeekQuestions).filter(
            WeekQuestions.quiz_id == quiz.id
        ).all()
        
        weeks = [wq.week_id for wq in week_qs]
        questions_count = len(json.loads(quiz.questions))
        
        quiz_list.append({
            "id": quiz.id,
            "title": quiz.title,
            "url": quiz.url,
            "questions_count": questions_count,
            "used_in_weeks": weeks,
            "created_at": quiz.created_at
        })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "quizzes": quiz_list
    }


@admin_router.get("/weeks/{week_id}/quizzes")
def get_week_quizzes_info(
    week_id: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Get all quiz information for a week WITHOUT questions."""
    logger.info(f"Admin fetching quiz info for week: {week_id}")
    
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.week_id == week_id
    ).all()
    
    if not week_qs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quizzes found for week {week_id}"
        )
    
    quiz_ids = [wq.quiz_id for wq in week_qs]
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    quiz_map = {q.id: q for q in quizzes}
    
    quiz_list = []
    for wq in week_qs:
        quiz = quiz_map.get(wq.quiz_id)
        if not quiz:
            continue
        
        selected = json.loads(wq.selected_indices)
        unselected = json.loads(wq.unselected_indices)
        
        quiz_list.append({
            "id": quiz.id,
            "week_question_id": wq.id,
            "title": quiz.title,
            "url": quiz.url,
            "total_questions": len(json.loads(quiz.questions)),
            "selected_count": len(selected),
            "unselected_count": len(unselected),
            "created_at": quiz.created_at
        })
    
    logger.info(f"Retrieved {len(quiz_list)} quizzes for week {week_id}")
    return {
        "week_id": week_id,
        "total_quizzes": len(quiz_list),
        "quizzes": quiz_list
    }


@admin_router.get("/quizzes/{quiz_id}/questions")
def get_quiz_questions(
    quiz_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Get all questions for a specific quiz."""
    logger.info(f"Admin fetching questions for quiz: {quiz_id}")
    
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    # Get weeks that use this quiz
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.quiz_id == quiz_id
    ).all()
    
    weeks_info = []
    for wq in week_qs:
        selected = json.loads(wq.selected_indices)
        unselected = json.loads(wq.unselected_indices)
        weeks_info.append({
            "week_id": wq.week_id,
            "selected_count": len(selected),
            "unselected_count": len(unselected)
        })
    
    questions = json.loads(quiz.questions)
    
    logger.info(f"Retrieved {len(questions)} questions for quiz {quiz_id}")
    return {
        "quiz_id": quiz.id,
        "title": quiz.title,
        "url": quiz.url,
        "used_in_weeks": weeks_info,
        "total_questions": len(questions),
        "questions": questions
    }


@admin_router.put("/weeks/{week_id}/questions/selection")
def update_question_selection(
    week_id: str,
    update_data: BulkQuestionSelectionUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Update which questions are selected/unselected for a week.
    New schema: Provide quiz_id and selected_indices. Unselected indices are calculated automatically.
    """
    logger.info(f"Admin updating question selection for {len(update_data.selections)} quizzes in week {week_id}")
    
    # Validate all quiz IDs exist
    quiz_ids = [sel.quiz_definition_id for sel in update_data.selections]  # Using quiz_definition_id as quiz_id for backwards compatibility
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    
    if len(quizzes) != len(quiz_ids):
        found_ids = [q.id for q in quizzes]
        missing_ids = [qid for qid in quiz_ids if qid not in found_ids]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quizzes not found: {missing_ids}"
        )
    
    quiz_map = {q.id: q for q in quizzes}
    
    # Validate indices and calculate total
    total_new_selections = 0
    validated_selections = []
    
    for selection in update_data.selections:
        quiz_id = selection.quiz_definition_id
        quiz = quiz_map[quiz_id]
        questions = json.loads(quiz.questions)
        max_index = len(questions) - 1
        
        # Validate indices
        invalid_indices = [i for i in selection.selected_indices if i < 0 or i > max_index]
        if invalid_indices:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid question indices for quiz {quiz_id}: {invalid_indices}. "
                       f"Quiz has {len(questions)} questions (indices 0-{max_index})."
            )
        
        # Calculate unselected indices
        all_indices = set(range(len(questions)))
        selected_set = set(selection.selected_indices)
        unselected_indices = list(all_indices - selected_set)
        
        validated_selections.append({
            'quiz_id': quiz_id,
            'quiz': quiz,
            'selected_indices': selection.selected_indices,
            'unselected_indices': unselected_indices
        })
        
        total_new_selections += len(selection.selected_indices)
    
    # Check if total is less than 100
    if total_new_selections < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot apply selection. Total selected questions is {total_new_selections}, but minimum required is 100."
        )
    
    # Check if total exceeds 100
    if total_new_selections > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot apply selection. Total selected questions is {total_new_selections}, but maximum is 100."
        )
    
    # Apply changes
    results = []
    
    for validated in validated_selections:
        quiz_id = validated['quiz_id']
        selected_indices = validated['selected_indices']
        unselected_indices = validated['unselected_indices']
        
        # Check if WeekQuestions entry exists
        week_q = db.query(WeekQuestions).filter(
            WeekQuestions.week_id == week_id,
            WeekQuestions.quiz_id == quiz_id
        ).first()
        
        if week_q:
            # Update existing entry
            old_selected = json.loads(week_q.selected_indices)
            week_q.selected_indices = json.dumps(selected_indices)
            week_q.unselected_indices = json.dumps(unselected_indices)
            
            results.append({
                "quiz_id": quiz_id,
                "week_question_id": week_q.id,
                "selected_count": len(selected_indices),
                "unselected_count": len(unselected_indices),
                "previous_selected_count": len(old_selected),
                "action": "updated"
            })
        else:
            # Create new entry with same created_at as quiz
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
            week_q = WeekQuestions(
                week_id=week_id,
                quiz_id=quiz_id,
                selected_indices=json.dumps(selected_indices),
                unselected_indices=json.dumps(unselected_indices),
                created_at=quiz.created_at if quiz else None
            )
            db.add(week_q)
            
            results.append({
                "quiz_id": quiz_id,
                "selected_count": len(selected_indices),
                "unselected_count": len(unselected_indices),
                "action": "created"
            })
    
    db.commit()
    
    # Update week summary
    update_week_summary(db, week_id)
    db.commit()
    
    logger.info(f"Updated selection for {len(results)} quizzes. Total selected: {total_new_selections}")
    return {
        "message": "Question selection updated successfully",
        "week_id": week_id,
        "total_quizzes_updated": len(results),
        "total_selected_questions": total_new_selections,
        "results": results
    }


@admin_router.get("/weeks/{week_id}/questions/all")
def get_all_week_questions_with_selection(
    week_id: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Get ALL questions for a week with selection status (admin view)."""
    logger.info(f"Admin fetching all questions with selection for week: {week_id}")
    
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.week_id == week_id
    ).all()
    
    if not week_qs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quizzes found for week {week_id}"
        )
    
    quiz_ids = [wq.quiz_id for wq in week_qs]
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    quiz_map = {q.id: q for q in quizzes}
    
    quiz_questions = []
    for wq in week_qs:
        quiz = quiz_map.get(wq.quiz_id)
        if not quiz:
            continue
            
        questions_data = json.loads(quiz.questions)
        selected_indices = json.loads(wq.selected_indices)
        
        questions_with_status = []
        for idx, q in enumerate(questions_data):
            questions_with_status.append({
                "index": idx,
                "selected": idx in selected_indices,
                **q
            })
        
        quiz_questions.append({
            "week_question_id": wq.id,
            "quiz_id": quiz.id,
            "quiz_title": quiz.title,
            "quiz_url": quiz.url,
            "total_questions": len(questions_data),
            "selected_count": len(selected_indices),
            "questions": questions_with_status
        })
    
    total_selected = sum(qd["selected_count"] for qd in quiz_questions)
    
    # Calculate total unselected questions
    total_unselected = sum(qd["total_questions"] - qd["selected_count"] for qd in quiz_questions)
    
    logger.info(f"Retrieved {len(quiz_questions)} quizzes with selection status for week {week_id}")
    return {
        "week_id": week_id,
        "total_quizzes": len(quiz_questions),
        "total_selected_questions": total_selected,
        "total_unselected_questions": total_unselected,
        "quizzes": quiz_questions
    }


@admin_router.get("/backup/all")
def get_all_backup_questions(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Get all backup quizzes (complete quizzes not used in any week)."""
    backup_quizzes = db.query(BackupQuestions).order_by(
        BackupQuestions.created_at.asc()
    ).all()
    
    result = []
    for bq in backup_quizzes:
        quiz = db.query(Quiz).filter(Quiz.id == bq.quiz_id).first()
        if quiz:
            indices = json.loads(bq.question_indices)
            questions_data = json.loads(quiz.questions)
            
            # Get actual questions
            questions = [questions_data[i] for i in indices if i < len(questions_data)]
            
            result.append({
                "backup_id": bq.id,
                "quiz_id": bq.quiz_id,
                "quiz_title": quiz.title,
                "quiz_url": quiz.url,
                "question_count": len(indices),
                "question_indices": indices,
                "created_at": bq.created_at,
                "questions": questions
            })
    
    return {
        "total_backup_quizzes": len(result),
        "backup_quizzes": result,
        "note": "Backup pile contains complete quizzes not used in any week"
    }


@admin_router.delete("/backup/{quiz_id}")
def delete_from_backup(
    quiz_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Delete a quiz from the backup pile."""
    backup = db.query(BackupQuestions).filter(
        BackupQuestions.quiz_id == quiz_id
    ).first()
    
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found in backup pile"
        )
    
    db.delete(backup)
    db.commit()
    
    logger.info(f"Admin deleted quiz {quiz_id} from backup pile")
    return {
        "message": f"Quiz {quiz_id} removed from backup pile",
        "quiz_id": quiz_id
    }


@admin_router.post("/quizzes/{quiz_id}/regenerate")
def regenerate_quiz_questions(
    quiz_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Re-scrape the article URL and generate new questions using the quiz generator service.
    This replaces all existing questions for the quiz with freshly scraped content.
    """
    from app.services.quiz_generator import generate_quiz
    from app.scraper import scrape_article
    
    logger.info(f"Admin regenerating questions for quiz {quiz_id}")
    
    # Get the quiz
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found"
        )
    
    # Check if quiz has article URL
    if not quiz.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz has no article URL to scrape from"
        )
    
    try:
        # Step 1: Scrape the article fresh from the URL
        logger.info(f"Scraping article from URL: {quiz.url}")
        article_data = scrape_article(quiz.url)
        
        # Update article text with fresh content
        quiz.article_text = article_data["full_text"]
        
        # Step 2: Generate new questions using OpenAI
        logger.info(f"Generating new questions for quiz {quiz_id}")
        quiz_json_str = generate_quiz(article_data["full_text"])
        quiz_data = json.loads(quiz_json_str)
        
        # Update quiz with new questions and title
        old_question_count = len(json.loads(quiz.questions))
        quiz.title = quiz_data.get("title", quiz.title)
        quiz.questions = json.dumps(quiz_data["questions"])
        new_question_count = len(quiz_data["questions"])
        
        # Update all WeekQuestions entries that reference this quiz
        week_qs = db.query(WeekQuestions).filter(
            WeekQuestions.quiz_id == quiz_id
        ).all()
        
        for wq in week_qs:
            # Reset selections - select first 10 (or however many exist)
            selected = list(range(min(10, new_question_count)))
            unselected = list(range(10, new_question_count))
            
            wq.selected_indices = json.dumps(selected)
            wq.unselected_indices = json.dumps(unselected)
            
            # Update week summary
            update_week_summary(db, wq.week_id)
        
        # Update backup questions if quiz is in backup
        backup = db.query(BackupQuestions).filter(
            BackupQuestions.quiz_id == quiz_id
        ).first()
        
        if backup:
            # All questions go to backup
            backup.question_indices = json.dumps(list(range(new_question_count)))
        
        db.commit()
        
        logger.info(f"Successfully regenerated quiz {quiz_id}: {old_question_count} → {new_question_count} questions")
        
        return {
            "message": "Quiz questions regenerated successfully",
            "quiz_id": quiz_id,
            "title": quiz.title,
            "old_question_count": old_question_count,
            "new_question_count": new_question_count,
            "weeks_updated": [wq.week_id for wq in week_qs]
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse generated quiz JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse generated quiz questions"
        )
    except Exception as e:
        logger.error(f"Error regenerating quiz {quiz_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate quiz: {str(e)}"
        )