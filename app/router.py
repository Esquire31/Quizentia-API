from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.scraper import scrape_article
from app.services.quiz_generator import generate_quiz
from app.services.listing_scraper import get_latest_article_urls
from app.schemas import QuizDefinitionResponse, QuizRequest, QuizResponse, WeeklyQuizGroup, GetQuizRequest
from app.database import get_db
from app.models import Quiz, QuizDefinition
from app.logging_config import get_logger
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
def scrape(url: str):
    logger.info(f"Scraping article from URL: {url}")
    article = scrape_article(url)
    logger.info(f"Scraped article: {article.get('title', 'Unknown')}")
    return article

@router.post("/generate_quiz", response_model=QuizResponse)
def generate_quiz_questions(payload: QuizRequest):
    try:
        logger.info(f"Generating quiz for URL: {payload.url}")
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
def scrape_urls():
    try:
        logger.info("Scraping latest article URLs")
        
        urls = get_latest_article_urls()
        
        logger.info(f"Retrieved {len(urls)} URLs")
        
        return {"urls": urls}
    
    except Exception as e:
        logger.error(f"Error scraping URLs: {str(e)}")
        
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingestion/weekly")
def weekly_ingestion(db: Session = Depends(get_db)):
    try:
        logger.info("Starting weekly ingestion process")
        
        urls = get_latest_article_urls()
        logger.info(f"Retrieved {len(urls)} URLs from listing scraper")
        
        if len(urls) < 12:
            logger.warning(f"Only {len(urls)} URLs available, need at least 12")
            raise HTTPException(status_code=400, detail="Not enough URLs scraped")

        quiz_ids = []
        total_questions = 0
        
        # Collect all valid quiz data first
        valid_quizzes = []
        
        for i, url in enumerate(urls[:12]):
            logger.info(f"Processing article {i+1}/12: {url}")
            
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
        
        # Generate week_id for this ingestion
        week_id = _generate_week_id(datetime.utcnow())
        
        # Save all valid quizzes in a single transaction
        for quiz_data in valid_quizzes:
            quiz_entry = Quiz(
                title=quiz_data['title'],
                url=quiz_data['url'],
                questions=json.dumps(quiz_data['questions'])
            )
            db.add(quiz_entry)
            db.flush()  # Get the ID
            
            quiz_definition_entry = QuizDefinition(
                quiz_id=quiz_entry.id,
                title=quiz_data['title'],
                week_id=week_id
            )
            db.add(quiz_definition_entry)
            
            quiz_ids.append(quiz_entry.id)
            total_questions += len(quiz_data['questions'])
            logger.info(f"Saved quiz for article with ID: {quiz_entry.id}")
        
        db.commit()
        logger.info(f"Total quizzes saved: {len(quiz_ids)}, Total questions: {total_questions}")

        return {
            "message": "Weekly ingestion completed",
            "quiz_ids": quiz_ids,
            "total_questions": total_questions,
            "week_id": week_id,
            "week_label": _format_week_label(datetime.utcnow())
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error in weekly ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quizzes/list", response_model=List[QuizDefinitionResponse])
def list_quizzes(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    quizzes = db.query(QuizDefinition).offset(skip).limit(limit).all()
    return quizzes


@router.get("/quizzes/weekly", response_model=List[WeeklyQuizGroup])
def list_weekly_quizzes(
    db: Session = Depends(get_db),
    max_weeks: int = Query(6, ge=1, le=52)
):
    quiz_definitions = db.query(QuizDefinition).order_by(QuizDefinition.created_at.desc()).all()
    if not quiz_definitions:
        return []

    week_buckets = {}
    for qd in quiz_definitions:
        week_id = qd.week_id
        if not week_id:
            # Fallback for old entries without week_id
            created_at = qd.created_at or datetime.utcnow()
            week_id = _generate_week_id(created_at)
        
        if week_id not in week_buckets:
            # Parse week_id to get the date for label
            created_at = qd.created_at or datetime.utcnow()
            week_buckets[week_id] = {
                "week_label": _format_week_label(created_at),
                "quiz_ids": [],
                "quizzes": [],
                "latest_created_at": created_at,
                "week_id_sort": week_id
            }

        bucket = week_buckets[week_id]
        bucket["latest_created_at"] = max(bucket["latest_created_at"], qd.created_at or datetime.utcnow())
        bucket["quiz_ids"].append(qd.quiz_id)
        bucket["quizzes"].append(qd)

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


@router.post("/quizzes/get", response_model=QuizResponse)
def get_quiz(
    payload: GetQuizRequest,
    db: Session = Depends(get_db)
):
    try:
        ids_to_fetch = payload.quiz_ids

        if ids_to_fetch:
            logger.info(f"Fetching quizzes with IDs: {ids_to_fetch}")

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
