from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.scraper import scrape_article
from app.services.quiz_generator import generate_quiz
from app.services.listing_scraper import get_latest_article_urls
from app.schemas import QuizRequest, QuizResponse
from app.database import get_db
from app.models import Quiz
import json
import logging

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
        for i, url in enumerate(urls[:12]):  # Take first 12
            logger.info(f"Processing article {i+1}/12: {url}")
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
            for q in questions[:10]:
                article_questions.append({
                    "question": q["question"],
                    "options": q["options"],
                    "correct_answer": q.get("answer") or q.get("correct_answer"),
                    "hint": q["hint"]
                })
            # Save to DB for this article
            quiz_entry = Quiz(
                title=article["title"],
                url=url,
                questions=json.dumps(article_questions)
            )
            db.add(quiz_entry)
            db.commit()
            db.refresh(quiz_entry)
            quiz_ids.append(quiz_entry.id)
            total_questions += len(article_questions)
            logger.info(f"Saved quiz for article to database with ID: {quiz_entry.id}")

        logger.info(f"Total quizzes saved: {len(quiz_ids)}, Total questions: {total_questions}")

        return {"message": "Weekly ingestion completed", "quiz_ids": quiz_ids, "total_questions": total_questions}

    except Exception as e:
        logger.error(f"Error in weekly ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))