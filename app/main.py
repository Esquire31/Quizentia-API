from fastapi import FastAPI
from app.scraper import scrape_article

app = FastAPI(title="Quizentia")


@app.get("/")
def health_check():
    return {"status": "running"}


@app.post("/scrape")
def scrape(url: str):
    article = scrape_article(url)
    return article
