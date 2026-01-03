# Admin API Documentation

## Authentication

### Login
**POST** `/admin/login`

Request:
```json
{
  "username": "admin",
  "password": "your_password"
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

**Use the token in all subsequent requests:**
```
Authorization: Bearer <access_token>
```

---

## Week Management

### Get All Questions in a Week
**GET** `/admin/weeks/{week_id}/questions`

Returns ALL questions (no 100 limit) for a specific week.

Response:
```json
{
  "week_id": "260101",
  "total_questions": 250,
  "questions": [
    {
      "quiz_id": 1,
      "quiz_title": "Article Title",
      "question": "What is...?",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "A",
      "hint": "Think about..."
    }
  ]
}
```

### Get Week Statistics
**GET** `/admin/weeks/{week_id}/stats`

Response:
```json
{
  "week_id": "260101",
  "total_quizzes": 5,
  "total_questions": 250,
  "can_delete_more": true
}
```

---

## Quiz Management

### List All Quizzes
**GET** `/admin/quizzes?skip=0&limit=50`

Response:
```json
{
  "total": 100,
  "skip": 0,
  "limit": 50,
  "quizzes": [
    {
      "id": 1,
      "title": "Article Title",
      "url": "https://...",
      "questions_count": 50,
      "week_id": "260101",
      "created_at": "2026-01-03T10:00:00"
    }
  ]
}
```

### Delete Entire Quiz
**DELETE** `/admin/quizzes/{quiz_id}`

⚠️ **Constraint:** Week must have at least 100 questions remaining after deletion.

Response:
```json
{
  "message": "Quiz 1 deleted successfully",
  "deleted_quiz_id": 1
}
```

Error (if would go below 100):
```json
{
  "detail": "Cannot delete quiz. Week must have at least 100 questions. Currently 150 questions, would have 50 after deletion."
}
```

---

## Question Management

### Delete a Question
**DELETE** `/admin/quizzes/{quiz_id}/questions/{question_index}`

⚠️ **Constraint:** Week must have at least 100 questions remaining after deletion.

- `question_index` starts at 0

Response:
```json
{
  "message": "Question deleted successfully",
  "deleted_question": {
    "question": "What is...?",
    "options": ["A", "B", "C", "D"],
    "correct_answer": "A",
    "hint": "Think about..."
  },
  "remaining_questions": 49,
  "week_total_questions": 249
}
```

### Update a Question
**PUT** `/admin/quizzes/{quiz_id}/questions/{question_index}`

Request (all fields optional):
```json
{
  "question": "Updated question?",
  "options": ["New A", "New B", "New C", "New D"],
  "correct_answer": "New A",
  "hint": "Updated hint"
}
```

Response:
```json
{
  "message": "Question updated successfully",
  "updated_question": {
    "question": "Updated question?",
    "options": ["New A", "New B", "New C", "New D"],
    "correct_answer": "New A",
    "hint": "Updated hint"
  }
}
```

---

## Setup

### 1. Add to .env file:
```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password_here
ADMIN_SECRET_KEY=your_random_32_char_secret_key_here
```

### 2. Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Install dependencies:
```bash
pip install python-jose[cryptography]
```

---

## Security Notes

- JWT tokens expire after 8 hours
- Tokens are validated on every admin request
- All admin endpoints require authentication
- Minimum 100 questions per week is enforced on all deletions
