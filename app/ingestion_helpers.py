"""
Helper functions for weekly quiz ingestion with new schema.
"""
from sqlalchemy.orm import Session
from app.models import Quiz, WeekQuestions, BackupQuestions, WeekSummary
from app.logging_config import get_logger
import json
from typing import List, Dict, Tuple

logger = get_logger(__name__)


def update_week_summary(db: Session, week_id: str) -> None:
    """Update or create week summary with current counts."""
    week_questions = db.query(WeekQuestions).filter(
        WeekQuestions.week_id == week_id
    ).all()
    
    total_selected = 0
    total_unselected = 0
    
    for wq in week_questions:
        selected = json.loads(wq.selected_indices)
        unselected = json.loads(wq.unselected_indices)
        total_selected += len(selected)
        total_unselected += len(unselected)
    
    # Update or create summary
    summary = db.query(WeekSummary).filter(WeekSummary.week_id == week_id).first()
    if summary:
        summary.total_selected = total_selected
        summary.total_unselected = total_unselected
        summary.total_quizzes = len(week_questions)
    else:
        summary = WeekSummary(
            week_id=week_id,
            total_selected=total_selected,
            total_unselected=total_unselected,
            total_quizzes=len(week_questions)
        )
        db.add(summary)
    
    logger.info(f"Updated week {week_id} summary: {total_selected} selected, {total_unselected} unselected, {len(week_questions)} quizzes")


def get_complete_quizzes_from_backup(db: Session, max_quizzes: int) -> List[Dict]:
    """
    Get complete quizzes from backup table.
    Returns list of {quiz_id, quiz, question_indices}.
    """
    logger.info(f"Fetching up to {max_quizzes} complete quizzes from backup")
    
    backup_quizzes = db.query(BackupQuestions).order_by(
        BackupQuestions.created_at.asc()
    ).limit(max_quizzes).all()
    
    result = []
    for bq in backup_quizzes:
        quiz = db.query(Quiz).filter(Quiz.id == bq.quiz_id).first()
        if not quiz:
            continue
        
        indices = json.loads(bq.question_indices)
        result.append({
            'backup_id': bq.id,
            'quiz_id': bq.quiz_id,
            'quiz': quiz,
            'question_indices': indices,
            'from_backup': True
        })
    
    logger.info(f"Retrieved {len(result)} complete quizzes from backup")
    return result


def get_questions_from_backup_individual(db: Session, no_questions: int) -> List[Dict]:
    """
    Get individual questions from backup table.
    Returns list of {backup_id, quiz_id, quiz, question_index}.
    """
    logger.info(f"Fetching {no_questions} individual questions from backup")
    
    backup_quizzes = db.query(BackupQuestions).order_by(
        BackupQuestions.created_at.asc()
    ).all()
    
    collected = []
    for bq in backup_quizzes:
        if len(collected) >= no_questions:
            break
        
        quiz = db.query(Quiz).filter(Quiz.id == bq.quiz_id).first()
        if not quiz:
            continue
        
        indices = json.loads(bq.question_indices)
        questions_data = json.loads(quiz.questions)
        
        for idx in indices:
            if len(collected) >= no_questions:
                break
            
            if idx < len(questions_data):
                collected.append({
                    'backup_id': bq.id,
                    'quiz_id': bq.quiz_id,
                    'quiz': quiz,
                    'question_index': idx,
                    'question': questions_data[idx],
                    'from_backup_individual': True
                })
    
    logger.info(f"Retrieved {len(collected)} individual questions from backup")
    return collected


def get_questions_from_previous_weeks_unselected(db: Session, no_questions: int, current_week_id: str) -> List[Dict]:
    """
    Get unselected questions from previous weeks (recent to old).
    Returns list of {week_id, quiz_id, quiz, question_index}.
    """
    logger.info(f"Fetching {no_questions} unselected questions from previous weeks")
    
    # Get all previous weeks (sorted desc - most recent first)
    all_weeks = db.query(WeekQuestions.week_id).distinct().order_by(
        WeekQuestions.week_id.desc()
    ).all()
    
    previous_weeks = [w[0] for w in all_weeks if w[0] < current_week_id]
    
    if not previous_weeks:
        logger.warning("No previous weeks found")
        return []
    
    collected = []
    for prev_week_id in previous_weeks:
        if len(collected) >= no_questions:
            break
        
        week_qs = db.query(WeekQuestions).filter(
            WeekQuestions.week_id == prev_week_id
        ).all()
        
        for wq in week_qs:
            if len(collected) >= no_questions:
                break
            
            quiz = db.query(Quiz).filter(Quiz.id == wq.quiz_id).first()
            if not quiz:
                continue
            
            unselected_indices = json.loads(wq.unselected_indices)
            questions_data = json.loads(quiz.questions)
            
            for idx in unselected_indices:
                if len(collected) >= no_questions:
                    break
                
                if idx < len(questions_data):
                    collected.append({
                        'week_id': prev_week_id,
                        'week_question_id': wq.id,
                        'quiz_id': wq.quiz_id,
                        'quiz': quiz,
                        'question_index': idx,
                        'question': questions_data[idx],
                        'from_previous_unselected': True
                    })
    
    logger.info(f"Retrieved {len(collected)} unselected questions from previous weeks")
    return collected


def get_questions_from_previous_weeks_selected(db: Session, no_questions: int, current_week_id: str) -> List[Dict]:
    """
    Get selected questions from previous weeks (recent to old) - LAST RESORT.
    Returns list of {week_id, quiz_id, quiz, question_index}.
    """
    logger.info(f"Fetching {no_questions} selected questions from previous weeks (last resort)")
    
    # Get all previous weeks (sorted desc)
    all_weeks = db.query(WeekQuestions.week_id).distinct().order_by(
        WeekQuestions.week_id.desc()
    ).all()
    
    previous_weeks = [w[0] for w in all_weeks if w[0] < current_week_id]
    
    if not previous_weeks:
        logger.warning("No previous weeks found")
        return []
    
    collected = []
    for prev_week_id in previous_weeks:
        if len(collected) >= no_questions:
            break
        
        week_qs = db.query(WeekQuestions).filter(
            WeekQuestions.week_id == prev_week_id
        ).all()
        
        for wq in week_qs:
            if len(collected) >= no_questions:
                break
            
            quiz = db.query(Quiz).filter(Quiz.id == wq.quiz_id).first()
            if not quiz:
                continue
            
            selected_indices = json.loads(wq.selected_indices)
            questions_data = json.loads(quiz.questions)
            
            for idx in selected_indices:
                if len(collected) >= no_questions:
                    break
                
                if idx < len(questions_data):
                    collected.append({
                        'week_id': prev_week_id,
                        'week_question_id': wq.id,
                        'quiz_id': wq.quiz_id,
                        'quiz': quiz,
                        'question_index': idx,
                        'question': questions_data[idx],
                        'from_previous_selected': True
                    })
    
    logger.info(f"Retrieved {len(collected)} selected questions from previous weeks")
    return collected


def remove_question_from_backup(db: Session, backup_id: int, question_index: int) -> None:
    """Remove a specific question index from a backup quiz."""
    backup = db.query(BackupQuestions).filter(BackupQuestions.id == backup_id).first()
    if not backup:
        return
    
    indices = json.loads(backup.question_indices)
    if question_index in indices:
        indices.remove(question_index)
        
        if not indices:
            # No more questions, delete backup entry
            db.delete(backup)
            logger.info(f"Deleted backup entry {backup_id} (no questions remaining)")
        else:
            backup.question_indices = json.dumps(indices)
            logger.info(f"Removed question {question_index} from backup {backup_id}")


def fill_week_to_target(db: Session, week_id: str, target_selected: int = 100) -> Tuple[int, int]:
    """
    Fill a week to reach target selected questions using priority:
    1. Complete quizzes from backup (if space allows)
    2. Individual questions from backup
    3. Previous weeks' unselected
    4. Previous weeks' selected
    
    Returns (questions_added, quizzes_added).
    """
    logger.info(f"Filling week {week_id} to {target_selected} selected questions")
    
    # Check current count
    summary = db.query(WeekSummary).filter(WeekSummary.week_id == week_id).first()
    current_selected = summary.total_selected if summary else 0
    
    if current_selected >= target_selected:
        logger.info(f"Week {week_id} already has {current_selected} selected questions")
        return 0, 0
    
    questions_needed = target_selected - current_selected
    logger.info(f"Need {questions_needed} more questions")
    
    questions_added = 0
    quizzes_added = 0
    
    # Priority 1: Try complete quizzes from backup
    space_for_quizzes = 12 - (summary.total_quizzes if summary else 0)
    if space_for_quizzes > 0:
        complete_quizzes = get_complete_quizzes_from_backup(db, space_for_quizzes)
        
        for cq in complete_quizzes:
            quiz = cq['quiz']
            indices = cq['question_indices']
            
            questions_to_take = min(len(indices), questions_needed - questions_added)
            if questions_to_take <= 0:
                break
            
            selected_indices = indices[:questions_to_take]
            unselected_indices = indices[questions_to_take:]
            
            # Check if this quiz already exists in the week
            existing_wq = db.query(WeekQuestions).filter(
                WeekQuestions.week_id == week_id,
                WeekQuestions.quiz_id == cq['quiz_id']
            ).first()
            
            if existing_wq:
                # Add to existing entry
                existing_selected = json.loads(existing_wq.selected_indices)
                existing_selected.extend(selected_indices)
                existing_wq.selected_indices = json.dumps(existing_selected)
                
                existing_unselected = json.loads(existing_wq.unselected_indices)
                existing_unselected.extend(unselected_indices)
                existing_wq.unselected_indices = json.dumps(existing_unselected)
            else:
                # Get quiz to use its created_at
                quiz = db.query(Quiz).filter(Quiz.id == cq['quiz_id']).first()
                
                # Create WeekQuestions entry
                week_q = WeekQuestions(
                    week_id=week_id,
                    quiz_id=cq['quiz_id'],
                    selected_indices=json.dumps(selected_indices),
                    unselected_indices=json.dumps(unselected_indices),
                    created_at=quiz.created_at if quiz else None
                )
                db.add(week_q)
                quizzes_added += 1
            
            questions_added += len(selected_indices)
            
            # Delete or update backup
            if not unselected_indices:
                db.delete(db.query(BackupQuestions).filter(BackupQuestions.id == cq['backup_id']).first())
            else:
                backup = db.query(BackupQuestions).filter(BackupQuestions.id == cq['backup_id']).first()
                backup.question_indices = json.dumps(unselected_indices)
            
            logger.info(f"Added complete quiz {cq['quiz_id']} with {len(selected_indices)} selected questions")
    
    # Priority 2: Individual questions from backup
    if questions_added < questions_needed:
        individual_qs = get_questions_from_backup_individual(db, questions_needed - questions_added)
        
        # Group by quiz_id
        by_quiz = {}
        for iq in individual_qs:
            quiz_id = iq['quiz_id']
            if quiz_id not in by_quiz:
                by_quiz[quiz_id] = []
            by_quiz[quiz_id].append(iq)
        
        for quiz_id, q_list in by_quiz.items():
            # Check if this quiz already in week
            existing_wq = db.query(WeekQuestions).filter(
                WeekQuestions.week_id == week_id,
                WeekQuestions.quiz_id == quiz_id
            ).first()
            
            indices_to_add = [q['question_index'] for q in q_list]
            
            if existing_wq:
                # Add to existing entry
                selected = json.loads(existing_wq.selected_indices)
                selected.extend(indices_to_add)
                existing_wq.selected_indices = json.dumps(selected)
            else:
                # Create new entry with same created_at as quiz
                quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
                week_q = WeekQuestions(
                    week_id=week_id,
                    quiz_id=quiz_id,
                    selected_indices=json.dumps(indices_to_add),
                    unselected_indices=json.dumps([]),
                    created_at=quiz.created_at if quiz else None
                )
                db.add(week_q)
                quizzes_added += 1
            
            # Remove from backup
            for q in q_list:
                remove_question_from_backup(db, q['backup_id'], q['question_index'])
            
            questions_added += len(indices_to_add)
            logger.info(f"Added {len(indices_to_add)} individual questions from quiz {quiz_id}")
    
    # Priority 3: Previous weeks' unselected
    if questions_added < questions_needed:
        unselected_qs = get_questions_from_previous_weeks_unselected(db, questions_needed - questions_added, week_id)
        
        # Process similar to individual questions
        by_quiz = {}
        for uq in unselected_qs:
            quiz_id = uq['quiz_id']
            if quiz_id not in by_quiz:
                by_quiz[quiz_id] = []
            by_quiz[quiz_id].append(uq)
        
        for quiz_id, q_list in by_quiz.items():
            existing_wq = db.query(WeekQuestions).filter(
                WeekQuestions.week_id == week_id,
                WeekQuestions.quiz_id == quiz_id
            ).first()
            
            indices_to_add = [q['question_index'] for q in q_list]
            
            if existing_wq:
                selected = json.loads(existing_wq.selected_indices)
                selected.extend(indices_to_add)
                existing_wq.selected_indices = json.dumps(selected)
            else:
                quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
                week_q = WeekQuestions(
                    week_id=week_id,
                    quiz_id=quiz_id,
                    selected_indices=json.dumps(indices_to_add),
                    unselected_indices=json.dumps([]),
                    created_at=quiz.created_at if quiz else None
                )
                db.add(week_q)
                quizzes_added += 1
            
            questions_added += len(indices_to_add)
            logger.info(f"Added {len(indices_to_add)} unselected questions from previous weeks, quiz {quiz_id}")
    
    # Priority 4: Previous weeks' selected (last resort)
    if questions_added < questions_needed:
        selected_qs = get_questions_from_previous_weeks_selected(db, questions_needed - questions_added, week_id)
        
        by_quiz = {}
        for sq in selected_qs:
            quiz_id = sq['quiz_id']
            if quiz_id not in by_quiz:
                by_quiz[quiz_id] = []
            by_quiz[quiz_id].append(sq)
        
        for quiz_id, q_list in by_quiz.items():
            existing_wq = db.query(WeekQuestions).filter(
                WeekQuestions.week_id == week_id,
                WeekQuestions.quiz_id == quiz_id
            ).first()
            
            indices_to_add = [q['question_index'] for q in q_list]
            
            if existing_wq:
                selected = json.loads(existing_wq.selected_indices)
                selected.extend(indices_to_add)
                existing_wq.selected_indices = json.dumps(selected)
            else:
                quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
                week_q = WeekQuestions(
                    week_id=week_id,
                    quiz_id=quiz_id,
                    selected_indices=json.dumps(indices_to_add),
                    unselected_indices=json.dumps([]),
                    created_at=quiz.created_at if quiz else None
                )
                db.add(week_q)
                quizzes_added += 1
            
            questions_added += len(indices_to_add)
            logger.info(f"Added {len(indices_to_add)} selected questions from previous weeks, quiz {quiz_id}")
    
    logger.info(f"Filled week {week_id}: added {questions_added} questions across {quizzes_added} quizzes")
    return questions_added, quizzes_added
