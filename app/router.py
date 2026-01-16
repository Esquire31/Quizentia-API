from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.scraper import scrape_article
from app.services.quiz_generator import generate_quiz
from app.services.listing_scraper import get_latest_article_urls
from app.schemas import (
    QuizDefinitionResponse, QuizRequest, QuizResponse, WeeklyQuizGroup, GetQuizRequest,
    QuizResultSubmit, QuizResultResponse, UserWeekResultSummary, UserResultHistory
)
from app.database import get_db
from app.models import Quiz, WeekQuestions, BackupQuestions, WeekSummary, UserQuizResult
from app.firebase_auth import get_current_user
from app.logging_config import get_logger
from app.ingestion_helpers import update_week_summary, fill_week_to_target
import json
from typing import List

logger = get_logger(__name__)

router = APIRouter()


def _generate_week_id(when: datetime = None) -> str:
    """Generate week ID like '251201' for first week of December 2025 (YYMMWW format)."""
    dt = when or datetime.utcnow()
    year = dt.year % 100  # Last 2 digits of year
    month = dt.month
    week_num = ((dt.day - 1) // 7) + 1
    return f"{year:02d}{month:02d}{week_num:02d}"


def _format_week_label(when: datetime) -> str:
    """Return labels like 'December 1st Week' based on the provided date."""
    dt = when or datetime.utcnow()
    week_num = ((dt.day - 1) // 7) + 1
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(week_num, "th")
    month_name = dt.strftime("%B")
    return f"{month_name} {week_num}{suffix} Week"


@router.get("/")
def health_check():
    return {"status": "running"}

@router.post("/scrape")
def scrape(url: str, user: dict = Depends(get_current_user)):
    logger.info(f"User {user['uid']} scraping article from URL: {url}")
    article = scrape_article(url)
    logger.info(f"Scraped article: {article.get('title', 'Unknown')}")
    return article

@router.post("/generate_quiz", response_model=QuizResponse)
def generate_quiz_questions(payload: QuizRequest, user: dict = Depends(get_current_user)):
    try:
        logger.info(f"User {user['uid']} generating quiz for URL: {payload.url}")
        article = scrape_article(payload.url)

        if not article["full_text"]:
            logger.warning("Empty article content")
            raise HTTPException(status_code=400, detail="Empty Article Content")

        quiz_response = generate_quiz(article["full_text"][:6000])
        logger.info("Quiz generated successfully")

        quiz_data = json.loads(quiz_response)

        normalized_questions = []
        for q in quiz_data.get("questions", []):
            normalized_questions.append({
                "question": q["question"],
                "options": q["options"],
                "correct_answer": q.get("answer") or q.get("correct_answer"),
                "hint": q["hint"]
            })

        return {
            "title": article["title"],
            "questions": normalized_questions
        }

    except Exception as e:
        logger.error(f"Error generating quiz: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/listing_scrape")
def scrape_urls(user: dict = Depends(get_current_user)):
    try:
        logger.info(f"User {user['uid']} scraping latest article URLs")
        
        urls = get_latest_article_urls()
        
        logger.info(f"Retrieved {len(urls)} URLs")
        
        return {"urls": urls}
    
    except Exception as e:
        logger.error(f"Error scraping URLs: {str(e)}")
        
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingestion/weekly")
def weekly_ingestion(db: Session = Depends(get_db)):
    """
    New ingestion logic:
    - Scrape articles (up to 20)
    - Keep first 12 successful articles for the week
    - Articles 13+ go to backup table (complete quizzes)
    - Distribute 100 questions sequentially across the 12 quizzes as selected
    - Remaining questions from those 12 quizzes go to unselected
    - If <100 questions available, fill using priority: backup > prev weeks unselected > prev weeks selected
    """
    try:
        logger.info("Starting NEW weekly ingestion process")
        
        urls = get_latest_article_urls()
        logger.info(f"Retrieved {len(urls)} URLs from listing scraper")

        # Collect all valid quiz data first
        valid_quizzes = []
        
        for i, url in enumerate(urls[:20]):
            logger.info(f"Processing article {i+1}/20: {url}")
            
            # Check if URL already ingested
            existing_quiz = db.query(Quiz).filter(Quiz.url == url).first()
            if existing_quiz:
                logger.info(f"Article already ingested, skipping URL: {url}")
                continue
            
            try:
                article = scrape_article(url)
                if not article["full_text"]:
                    logger.warning(f"Empty content for URL: {url}")
                    continue
                
                logger.info(f"Scraped article: {article['title']}")
                logger.info("Generating quiz for the article")
                
                quiz_response = generate_quiz(article["full_text"][:6000])
                quiz_data = json.loads(quiz_response)
                questions = quiz_data.get("questions", [])
                logger.info(f"Generated {len(questions)} questions for article")
                
                # Take up to 10 questions per article
                article_questions = []
                quiz_title = quiz_data.get("title", article["title"])
                for q in questions[:10]:
                    article_questions.append({
                        "question": q["question"],
                        "options": q["options"],
                        "correct_answer": q.get("answer") or q.get("correct_answer"),
                        "hint": q["hint"]
                    })
                
                valid_quizzes.append({
                    'title': quiz_title,
                    'url': url,
                    'questions': article_questions
                })
                
            except Exception as e:
                logger.error(f"Error processing URL {url}: {str(e)}")
                continue
        
        if not valid_quizzes:
            raise HTTPException(status_code=400, detail="No valid quizzes scraped")
        
        logger.info(f"Successfully scraped {len(valid_quizzes)} quizzes")
        
        # Generate week_id for this ingestion
        week_id = _generate_week_id(datetime.utcnow())
        
        # Split: First 12 quizzes for the week, rest go to backup
        week_quizzes = valid_quizzes[:12]
        backup_quizzes = valid_quizzes[12:]
        
        logger.info(f"Week gets {len(week_quizzes)} quizzes, {len(backup_quizzes)} go to backup")
        
        # Save week quizzes
        saved_quiz_ids = []
        total_questions_available = 0
        
        for quiz_data in week_quizzes:
            # Create Quiz entry
            quiz_entry = Quiz(
                title=quiz_data['title'],
                url=quiz_data['url'],
                questions=json.dumps(quiz_data['questions'])
            )
            db.add(quiz_entry)
            db.flush()  # Get the ID
            
            saved_quiz_ids.append(quiz_entry.id)
            total_questions_available += len(quiz_data['questions'])
            logger.info(f"Saved quiz ID {quiz_entry.id} with {len(quiz_data['questions'])} questions")
        
        logger.info(f"Total questions available from {len(week_quizzes)} quizzes: {total_questions_available}")
        
        # Distribute 100 questions sequentially across quizzes
        questions_to_select = min(100, total_questions_available)
        remaining_to_select = questions_to_select
        
        for quiz_id in saved_quiz_ids:
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
            questions = json.loads(quiz.questions)
            total_q = len(questions)
            
            # How many to select from this quiz
            to_select = min(remaining_to_select, total_q)
            
            selected_indices = list(range(to_select))
            unselected_indices = list(range(to_select, total_q))
            
            # Create WeekQuestions entry with same created_at as quiz
            week_q = WeekQuestions(
                week_id=week_id,
                quiz_id=quiz_id,
                selected_indices=json.dumps(selected_indices),
                unselected_indices=json.dumps(unselected_indices),
                created_at=quiz.created_at
            )
            db.add(week_q)
            
            remaining_to_select -= to_select
            logger.info(f"Quiz {quiz_id}: {to_select} selected, {len(unselected_indices)} unselected")
            
            if remaining_to_select <= 0:
                break
        
        # If we still have quizzes that weren't touched (all their questions are unselected)
        if remaining_to_select <= 0:
            # Find quizzes that weren't added yet
            added_quiz_ids = db.query(WeekQuestions.quiz_id).filter(
                WeekQuestions.week_id == week_id
            ).all()
            added_quiz_ids = [q[0] for q in added_quiz_ids]
            
            for quiz_id in saved_quiz_ids:
                if quiz_id not in added_quiz_ids:
                    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
                    questions = json.loads(quiz.questions)
                    total_q = len(questions)
                    
                    # All questions are unselected
                    week_q = WeekQuestions(
                        week_id=week_id,
                        quiz_id=quiz_id,
                        selected_indices=json.dumps([]),
                        unselected_indices=json.dumps(list(range(total_q))),
                        created_at=quiz.created_at
                    )
                    db.add(week_q)
                    logger.info(f"Quiz {quiz_id}: 0 selected, {total_q} unselected")
        
        # Save backup quizzes (articles 13+)
        for quiz_data in backup_quizzes:
            # Create Quiz entry
            quiz_entry = Quiz(
                title=quiz_data['title'],
                url=quiz_data['url'],
                questions=json.dumps(quiz_data['questions'])
            )
            db.add(quiz_entry)
            db.flush()
            
            # Add all questions to backup
            all_indices = list(range(len(quiz_data['questions'])))
            backup_entry = BackupQuestions(
                quiz_id=quiz_entry.id,
                question_indices=json.dumps(all_indices)
            )
            db.add(backup_entry)
            logger.info(f"Added quiz {quiz_entry.id} to backup with {len(all_indices)} questions")
        
        db.commit()
        
        # Update week summary
        update_week_summary(db, week_id)
        db.commit()
        
        # Check if we need to fill gaps (if <100 selected)
        summary = db.query(WeekSummary).filter(WeekSummary.week_id == week_id).first()
        current_selected = summary.total_selected if summary else 0
        
        if current_selected < 100:
            logger.info(f"Only {current_selected} questions selected, filling to 100...")
            questions_added, quizzes_added = fill_week_to_target(db, week_id, target_selected=100)
            db.commit()
            
            # Update summary again
            update_week_summary(db, week_id)
            db.commit()
            
            logger.info(f"Filled {questions_added} questions from {quizzes_added} quizzes")
        
        # Final stats
        final_summary = db.query(WeekSummary).filter(WeekSummary.week_id == week_id).first()
        
        logger.info(f"Weekly ingestion completed for week {week_id}")
        return {
            "message": "Weekly ingestion completed successfully",
            "week_id": week_id,
            "week_label": _format_week_label(datetime.utcnow()),
            "new_quizzes_scraped": len(valid_quizzes),
            "week_quizzes": len(week_quizzes),
            "backup_quizzes": len(backup_quizzes),
            "total_selected": final_summary.total_selected if final_summary else 0,
            "total_unselected": final_summary.total_unselected if final_summary else 0,
            "total_quizzes": final_summary.total_quizzes if final_summary else 0
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error in weekly ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quizzes/list", response_model=List[QuizDefinitionResponse])
def list_quizzes(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    logger.info(f"User {user['uid']} listing quizzes")
    week_questions = db.query(WeekQuestions).offset(skip).limit(limit).all()
    # Convert to compatible format
    result = []
    for wq in week_questions:
        result.append({
            "id": wq.id,
            "quiz_id": wq.quiz_id,
            "week_id": wq.week_id,
            "title": db.query(Quiz).filter(Quiz.id == wq.quiz_id).first().title if db.query(Quiz).filter(Quiz.id == wq.quiz_id).first() else "Unknown",
            "created_at": wq.created_at
        })
    return result


@router.get("/quizzes/weekly", response_model=List[WeeklyQuizGroup])
def list_weekly_quizzes(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    max_weeks: int = Query(6, ge=1, le=52)
):
    logger.info(f"User {user['uid']} listing weekly quizzes")
    week_questions = db.query(WeekQuestions).order_by(WeekQuestions.created_at.desc()).all()
    if not week_questions:
        return []

    # Get all unique quiz_ids to fetch Quiz data
    all_quiz_ids = list(set(wq.quiz_id for wq in week_questions))
    quizzes = db.query(Quiz).filter(Quiz.id.in_(all_quiz_ids)).all()
    quiz_map = {q.id: q for q in quizzes}

    week_buckets = {}
    for wq in week_questions:
        week_id = wq.week_id
        
        if week_id not in week_buckets:
            # Parse week_id to get the date for label
            created_at = wq.created_at or datetime.utcnow()
            week_buckets[week_id] = {
                "week_label": _format_week_label(created_at),
                "quiz_ids": [],
                "quizzes": [],
                "latest_created_at": created_at,
                "week_id_sort": week_id
            }

        bucket = week_buckets[week_id]
        bucket["latest_created_at"] = max(bucket["latest_created_at"], wq.created_at or datetime.utcnow())
        bucket["quiz_ids"].append(wq.quiz_id)
        
        # Build proper QuizDefinitionResponse object
        quiz = quiz_map.get(wq.quiz_id)
        if quiz:
            selected_indices = json.loads(wq.selected_indices)
            bucket["quizzes"].append({
                "id": wq.id,
                "quiz_id": wq.quiz_id,
                "title": quiz.title,
                "week_id": wq.week_id,
                "selected_questions": selected_indices,
                "created_at": wq.created_at
            })

    ordered = sorted(week_buckets.values(), key=lambda b: b["week_id_sort"], reverse=True)
    trimmed = ordered[:max_weeks]

    return [
        {
            "week_label": bucket["week_label"],
            "week_id": bucket.get("week_id_sort"),
            "quiz_ids": bucket["quiz_ids"],
            "quizzes": bucket["quizzes"]
        }
        for bucket in trimmed
    ]


@router.get("/quizzes/weekly/{week_id}/questions")
def get_weekly_questions(
    week_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get SELECTED questions for a specific week (public API)."""
    logger.info(f"User {user['uid']} fetching questions for week: {week_id}")
    
    week_qs = db.query(WeekQuestions).filter(
        WeekQuestions.week_id == week_id
    ).all()
    
    if not week_qs:
        raise HTTPException(
            status_code=404,
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
        
        # Get selected questions only
        selected_indices = json.loads(wq.selected_indices)
        selected = [questions_data[i] for i in selected_indices 
                   if 0 <= i < len(questions_data)]
        
        for idx, q in enumerate(selected):
            all_questions.append({
                "quiz_id": quiz.id,
                "quiz_title": quiz.title,
                "quiz_url": quiz.url,
                **q
            })
    
    logger.info(f"Retrieved {len(all_questions)} selected questions for week {week_id}")
    return {
        "week_id": week_id,
        "total_questions": len(all_questions),
        "questions": all_questions
    }


@router.post("/quizzes/get", response_model=QuizResponse)
def get_quiz(
    payload: GetQuizRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    try:
        ids_to_fetch = payload.quiz_ids

        if ids_to_fetch:
            logger.info(f"User {user['uid']} fetching quizzes with IDs: {ids_to_fetch}")

            quizzes = db.query(Quiz).filter(Quiz.id.in_(ids_to_fetch)).all()
            if not quizzes:
                raise HTTPException(status_code=404, detail="Quiz not found")

            quiz_map = {quiz.id: quiz for quiz in quizzes}
            missing_ids = [qid for qid in ids_to_fetch if qid not in quiz_map]
            if missing_ids:
                raise HTTPException(status_code=404, detail=f"Quiz IDs not found: {missing_ids}")

            ordered_quizzes = [quiz_map[qid] for qid in ids_to_fetch]
            questions = []
            for quiz in ordered_quizzes:
                quiz_questions = json.loads(quiz.questions)
                questions.extend(quiz_questions)

            quiz_title = ordered_quizzes[0].title if len(ordered_quizzes) == 1 else "Selected Quizzes"

        else:
            logger.info("Quiz ID not provided, fetching latest 10 quizzes")
            
            # Fetch the latest 10 quizzes if no ID is provided
            latest_quizzes = db.query(Quiz).order_by(Quiz.id.desc()).limit(10).all()
            if not latest_quizzes:
                raise HTTPException(status_code=404, detail="No quizzes found")
            
            # Aggregate questions from the latest quizzes
            questions = []
            for quiz in latest_quizzes:
                quiz_questions = json.loads(quiz.questions)
                questions.extend(quiz_questions)
                # Count number of questions added
            logger.info(f"Added {len(questions)} questions")

            quiz_title = "Latest Quizzes"
        
        return {
            "title": quiz_title,
            "questions": questions
        }
    
    except Exception as e:
        logger.error(f"Error fetching quiz: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quizzes/results", response_model=QuizResultResponse)
def submit_quiz_result(
    result: QuizResultSubmit,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Submit quiz results for a week. Keeps track of attempts and best score."""
    user_id = user['uid']
    week_id = result.week_id
    
    logger.info(f"User {user_id} submitting results for week {week_id}")
    
    # Validate week exists
    week_summary = db.query(WeekSummary).filter(WeekSummary.week_id == week_id).first()
    if not week_summary:
        raise HTTPException(
            status_code=404,
            detail=f"Week {week_id} not found"
        )
    
    # Get all WeekQuestions for this week to validate answers
    week_questions = db.query(WeekQuestions).filter(
        WeekQuestions.week_id == week_id
    ).all()
    
    if not week_questions:
        raise HTTPException(
            status_code=404,
            detail=f"No questions found for week {week_id}"
        )
    
    # Build quiz map for validation
    quiz_ids = [wq.quiz_id for wq in week_questions]
    quizzes = db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).all()
    quiz_map = {q.id: json.loads(q.questions) for q in quizzes}
    
    # Calculate score and validate answers
    correct_count = 0
    validated_answers = []
    
    for answer in result.answers:
        if answer.quiz_id not in quiz_map:
            raise HTTPException(
                status_code=400,
                detail=f"Quiz {answer.quiz_id} not found in week {week_id}"
            )
        
        questions = quiz_map[answer.quiz_id]
        if answer.question_index < 0 or answer.question_index >= len(questions):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid question index {answer.question_index} for quiz {answer.quiz_id}"
            )
        
        question = questions[answer.question_index]
        is_correct = answer.selected_answer == question['correct_answer']
        
        if is_correct:
            correct_count += 1
        
        validated_answers.append({
            'quiz_id': answer.quiz_id,
            'question_index': answer.question_index,
            'selected_answer': answer.selected_answer,
            'is_correct': is_correct
        })
    
    total_questions = len(result.answers)
    percentage = (correct_count / total_questions * 100) if total_questions > 0 else 0
    
    # Get current attempt count for this user/week
    existing_attempts = db.query(UserQuizResult).filter(
        UserQuizResult.user_id == user_id,
        UserQuizResult.week_id == week_id
    ).count()
    
    attempt_number = existing_attempts + 1
    
    # Get current best score
    best_result = db.query(UserQuizResult).filter(
        UserQuizResult.user_id == user_id,
        UserQuizResult.week_id == week_id,
        UserQuizResult.is_best == True
    ).first()
    
    is_new_best = False
    is_best = False
    
    if best_result is None:
        # First attempt is always the best
        is_best = True
        is_new_best = True
    elif correct_count > best_result.score:
        # New best score
        is_best = True
        is_new_best = True
        # Mark previous best as not best
        best_result.is_best = False
    
    # Create new result
    new_result = UserQuizResult(
        user_id=user_id,
        week_id=week_id,
        score=correct_count,
        total_questions=total_questions,
        answers=json.dumps(validated_answers),
        attempt_number=attempt_number,
        is_best=is_best
    )
    
    db.add(new_result)
    db.commit()
    db.refresh(new_result)
    
    logger.info(f"User {user_id} completed week {week_id}: {correct_count}/{total_questions} (attempt #{attempt_number}, best: {is_best})")
    
    return QuizResultResponse(
        id=new_result.id,
        user_id=new_result.user_id,
        week_id=new_result.week_id,
        score=new_result.score,
        total_questions=new_result.total_questions,
        percentage=percentage,
        attempt_number=new_result.attempt_number,
        is_best=new_result.is_best,
        is_new_best=is_new_best,
        completed_at=new_result.completed_at
    )


@router.get("/users/results/history", response_model=UserResultHistory)
def get_user_result_history(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get user's quiz result history across all weeks."""
    user_id = user['uid']
    
    logger.info(f"Fetching result history for user {user_id}")
    
    # Get all results for this user grouped by week
    results = db.query(UserQuizResult).filter(
        UserQuizResult.user_id == user_id
    ).all()
    
    if not results:
        return UserResultHistory(
            user_id=user_id,
            total_weeks_attempted=0,
            results_by_week=[]
        )
    
    # Group by week
    weeks = {}
    for result in results:
        week_id = result.week_id
        if week_id not in weeks:
            weeks[week_id] = []
        weeks[week_id].append(result)
    
    # Build summary for each week
    results_by_week = []
    for week_id, week_results in weeks.items():
        best_result = next((r for r in week_results if r.is_best), week_results[0])
        last_attempt = max(week_results, key=lambda r: r.completed_at)
        
        best_percentage = (best_result.score / best_result.total_questions * 100) if best_result.total_questions > 0 else 0
        
        results_by_week.append(UserWeekResultSummary(
            week_id=week_id,
            best_score=best_result.score,
            best_percentage=best_percentage,
            total_attempts=len(week_results),
            last_attempt_at=last_attempt.completed_at,
            best_attempt_number=best_result.attempt_number
        ))
    
    # Sort by week_id descending (most recent first)
    results_by_week.sort(key=lambda x: x.week_id, reverse=True)
    
    return UserResultHistory(
        user_id=user_id,
        total_weeks_attempted=len(weeks),
        results_by_week=results_by_week
    )


@router.get("/users/results/week/{week_id}")
def get_user_week_result(
    week_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get user's results for a specific week including all attempts."""
    user_id = user['uid']
    
    logger.info(f"Fetching week {week_id} results for user {user_id}")
    
    results = db.query(UserQuizResult).filter(
        UserQuizResult.user_id == user_id,
        UserQuizResult.week_id == week_id
    ).order_by(desc(UserQuizResult.attempt_number)).all()
    
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No results found for week {week_id}"
        )
    
    return {
        "week_id": week_id,
        "total_attempts": len(results),
        "attempts": [
            {
                "id": r.id,
                "attempt_number": r.attempt_number,
                "score": r.score,
                "total_questions": r.total_questions,
                "percentage": (r.score / r.total_questions * 100) if r.total_questions > 0 else 0,
                "is_best": r.is_best,
                "completed_at": r.completed_at,
                "answers": json.loads(r.answers)
            }
            for r in results
        ]
    }
