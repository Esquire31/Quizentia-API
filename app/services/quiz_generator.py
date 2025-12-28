from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

PROMPT = """
You are an expert quiz creator.

You will receive an article.
Generate EXACTLY 10 multiple-choice questions.

Rules:
- Each question must have 4 options
- Only one correct answer
- Jumble the options so the correct answer is not always in the same position. Make it unpredictable.
- Provide a short helpful hint
- Questions must be factual and based only on the article
- Generate an interesting quiz title based on article content
- Output must be in JSON format as specified below
- Output MUST be valid JSON
{
  "title": "string",
  "questions": [
    {
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "one of the options",
      "hint": "string"
    }
  ]
}

- DO NOT use the word "answer".
- DO NOT add explanations.
- DO NOT wrap in markdown.
- DO NOT include explanations or markdown
- DO NOT reference the article in anyway in the question, just mention in the recent case of xyz case or in the judgement of xyz case
"""


def generate_quiz(article_text: str):
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": article_text}
        ],
        temperature=0.4
    )
    return response.choices[0].message.content
