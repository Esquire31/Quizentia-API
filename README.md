# Quizentia 🚀  
**Turn any article into engaging quizzes — instantly.**

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Build](https://img.shields.io/badge/build-active-brightgreen.svg)
![AI Powered](https://img.shields.io/badge/AI-powered-purple.svg)

---

## 🧠 About Quizentia

**Quizentia** is an AI-powered API platform that transforms any publicly accessible article into structured, high-quality quizzes.  
Designed to be content-agnostic, Quizentia works across domains — news, education, research, blogs, and more.

From scraping article content to generating intelligent quiz questions, Quizentia acts as a **one-stop backend engine** for quiz-based learning experiences.

---

## ✨ Key Features

- 🌐 Scrape and parse articles from public websites  
- 🧹 Clean and structure article content automatically  
- 🤖 Generate quizzes using AI (GPT-powered)  
- 🧩 Domain-agnostic — works for *any* topic  
- ⚡ Built with FastAPI for speed and scalability  
- 📦 JSON-first responses for easy integration  

---

## 🏗️ Tech Stack

- **Backend:** FastAPI (Python)
- **Scraping:** Requests + BeautifulSoup
- **AI:** OpenAI GPT (mini / configurable)
- **Parsing:** lxml
- **API Docs:** Swagger (auto-generated)

---

## 📂 Project Structure

```text
quizentia/
│
├── app/
│   ├── main.py          # FastAPI entry point
│   ├── scraper.py       # Article scraping logic
│   ├── schemas.py       # Pydantic models
│   └── services/
│       └── quiz_gen.py  # AI quiz generation
│
├── requirements.txt
└── README.md
````

---

## 🚀 Getting Started

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-username/quizentia.git
cd quizentia
```

### 2️⃣ Setup Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Run the API

```bash
uvicorn app.main:app --reload
```

Open API docs at:
👉 `http://127.0.0.1:8000/docs`

---

## 📡 Example API Response

```json
{
  "title": "Understanding Artificial Intelligence",
  "content": [
    "Artificial intelligence refers to...",
    "Machine learning is a subset of AI..."
  ],
  "quiz": [
    {
      "question": "What is artificial intelligence?",
      "options": ["...", "...", "...", "..."],
      "correct_answer": "..."
    }
  ]
}
```

---

## 🧪 Use Cases

* Quiz-based learning platforms
* EdTech applications
* News & content engagement tools
* Interview preparation systems
* Knowledge assessment engines

---

## 🔐 Ethical Use & Scraping

Quizentia is designed to work only with **publicly accessible content**.
Users are responsible for complying with website terms of service and applicable laws.

---

## 🛣️ Roadmap

* [ ] Multi-article batch processing
* [ ] Difficulty-based quiz generation
* [ ] User analytics & scoring
* [ ] Caching & rate limiting
* [ ] Multi-language support

---

## ⭐️ Support

If you find Quizentia useful, consider giving it a ⭐️ on GitHub.

---

