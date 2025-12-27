from fastapi import APIRouter, HTTPException
from app.scraper import scrape_article
from app.services.quiz_generator import generate_quiz
from app.services.listing_scraper import get_latest_article_urls
from app.schemas import QuizRequest, QuizResponse
import json

router = APIRouter()

@router.get("/")
def health_check():
    return {"status": "running"}

@router.post("/scrape")
def scrape(url: str):
    article = scrape_article(url)
    return article

@router.post("/generate_quiz", response_model=QuizResponse)
def generate_quiz_questions(payload: QuizRequest):
    try:
        article = scrape_article(payload.url)

        if not article["full_text"]:
            raise HTTPException(status_code=400, detail="Empty Article Content")

        quiz_response = generate_quiz(article["full_text"][:6000])

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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/listing_scrape")
def scrape_urls():
    try:
        urls = get_latest_article_urls()
        return {"urls": urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))