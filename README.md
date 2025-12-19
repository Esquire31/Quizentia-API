# Quizentia API 🚀

**Turn any article into engaging quizzes — instantly.**

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Build](https://img.shields.io/badge/build-active-brightgreen.svg)
![AI Powered](https://img.shields.io/badge/AI-powered-purple.svg)

---

## 🧠 About Quizentia

**Quizentia** is an AI-powered API that converts **any publicly accessible article** into a structured, interactive quiz.

It handles the entire pipeline:
**scraping → cleaning → understanding → quiz generation**, making it a one-stop backend engine for quiz-based products, learning platforms, and content engagement tools.

Quizentia is **domain-agnostic** — it works for news, blogs, education, research, tech, law, finance, and more.

---

## ✨ Key Features

* 🌐 Scrape articles from public websites
* 🧹 Clean & extract meaningful article text
* 🤖 Generate **10 AI-powered MCQs** per article
* 💡 Each question includes a **hint**
* 🧩 Topic-agnostic (not limited to any domain)
* ⚡ Built with FastAPI for performance
* 🔓 CORS-enabled for frontend integrations
* 📦 JSON-first, frontend-friendly API responses

---

## 🏗️ Tech Stack

* **Backend:** FastAPI (Python)
* **Scraping:** Requests + BeautifulSoup
* **AI:** OpenAI GPT (Mini / configurable)
* **Validation:** Pydantic
* **API Docs:** Swagger UI (auto-generated)

---

## 📂 Project Structure

```text
quizentia/
│
├── app/
│   ├── main.py              # FastAPI entry point + CORS
│   ├── scraper.py           # Article scraping logic
│   ├── schemas.py           # Pydantic request/response models
│   └── services/
│       └── quiz_generator.py # OpenAI quiz generation logic
│
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-username/quizentia.git
cd quizentia
```

### 2️⃣ Create & Activate Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Set Environment Variables

```bash
export OPENAI_API_KEY=your_api_key_here
```

(Windows PowerShell)

```powershell
setx OPENAI_API_KEY "your_api_key_here"
```

---

### 5️⃣ Run the API

```bash
uvicorn app.main:app --reload
```

📘 API Docs available at:
👉 **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**

---

## 📡 API Endpoints

### 🔹 Health Check

```
GET /
```

**Response**

```json
{ "status": "running" }
```

---

### 🔹 Generate Quiz from Article

```
POST /generate_quiz
```

**Request Body**

```json
{
  "url": "https://example.com/article"
}
```

---

### ✅ Successful Response

```json
{
  "title": "Article Title Here",
  "questions": [
    {
      "question": "What is the main idea of the article?",
      "options": [
        "Option A",
        "Option B",
        "Option C",
        "Option D"
      ],
      "correct_answer": "Option B",
      "hint": "Focus on the core argument discussed."
    }
  ]
}
```

* Always returns **10 questions**
* Each question has **4 options**
* Includes a **hint** for better UX

---

## 🧪 Use Cases

* Quiz-based learning platforms
* EdTech applications
* Article-to-quiz SaaS products
* News engagement tools
* Interview preparation systems
* Knowledge assessment engines

---

## 🔐 Ethical Use & Scraping

Quizentia only supports **publicly accessible content**.

Users are responsible for:

* Respecting website terms of service
* Complying with copyright laws
* Using generated quizzes ethically

---

## 🛣️ Roadmap

* [ ] Difficulty-based quiz generation
* [ ] Multi-article batch processing
* [ ] Async & streaming quiz generation
* [ ] Rate limiting & API keys
* [ ] Caching for repeated URLs
* [ ] Multi-language quiz support
* [ ] Analytics & scoring APIs

---

## ⭐ Support

If you find **Quizentia** useful, consider giving it a ⭐️ on GitHub — it really helps!


Just say the word 🚀
