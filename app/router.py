from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.scraper import scrape_article
from app.services.quiz_generator import generate_quiz
from app.services.listing_scraper import get_latest_article_urls
from app.schemas import QuizDefinitionResponse, QuizRequest, QuizResponse
from app.database import get_db
from app.models import Quiz, QuizDefinition
import json
import logging
from typing import List
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

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
                title=quiz_data['title']
            )
            db.add(quiz_definition_entry)
            
            quiz_ids.append(quiz_entry.id)
            total_questions += len(quiz_data['questions'])
            logger.info(f"Saved quiz for article with ID: {quiz_entry.id}")
        
        db.commit()
        logger.info(f"Total quizzes saved: {len(quiz_ids)}, Total questions: {total_questions}")

        return {"message": "Weekly ingestion completed", "quiz_ids": quiz_ids, "total_questions": total_questions}

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


@router.get("/quizzes/get", response_model=QuizResponse)
def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    try:
        logger.info(f"Fetching quiz with ID: {quiz_id}")
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        questions = json.loads(quiz.questions)
        
        return {
            "title": quiz.title,
            "questions": questions
        }
    
    except Exception as e:
        logger.error(f"Error fetching quiz: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# One-time migration endpoint to create QuizDefinition entries for existing Quiz records
# @router.post("/migrate/quiz_definitions")
# def migrate_quiz_definitions(db: Session = Depends(get_db)):
#     """One-time migration to create QuizDefinition entries for existing Quiz records"""
#     try:
#         logger.info("Starting QuizDefinition migration")
        
#         # Get all Quiz records that don't have a corresponding QuizDefinition
#         existing_quiz_ids_subquery = select(QuizDefinition.quiz_id)
#         quizzes_without_definition = db.query(Quiz).filter(~Quiz.id.in_(existing_quiz_ids_subquery)).all()
        
#         migrated_count = 0
#         for quiz in quizzes_without_definition:
#             quiz_definition = QuizDefinition(
#                 quiz_id=quiz.id,
#                 title=quiz.title
#             )
#             db.add(quiz_definition)
#             migrated_count += 1
#             logger.info(f"Created QuizDefinition for Quiz ID: {quiz.id}")
        
#         db.commit()
#         logger.info(f"Migration completed. Created {migrated_count} QuizDefinition entries")
        
#         return {
#             "message": "Migration completed successfully", 
#             "migrated_count": migrated_count
#         }
    
#     except Exception as e:
#         db.rollback()
#         logger.error(f"Migration failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

