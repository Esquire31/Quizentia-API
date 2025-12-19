from fastapi import FastAPI, HTTPException
from app.scraper import scrape_article
from app.services.quiz_generator import generate_quiz
from app.schemas import QuizResponse
import json

app = FastAPI(title="Quizentia")


@app.get("/")
def health_check():
    return {"status": "running"}


@app.post("/scrape")
def scrape(url: str):
    article = scrape_article(url)
    return article


@app.post("/generate_quiz", response_model=QuizResponse)
def generate_quiz_questions(url: str):
    try:
        article = scrape_article(url)

        article_text = article["full_text"][:6000]

        quiz_response = generate_quiz(article_text)

        quiz_data = json.loads(quiz_response)

        normalized_questions = []

        for q in quiz_data["questions"]:
            normalized_questions.append({
                "question": q["question"],
                "options": q["options"],
                "correct_answer": q["answer"],
                "hint": q["hint"]
            })

        return {
            "title": article["title"],
            "questions": normalized_questions
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

