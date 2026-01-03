from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from app.router import router
from app.admin_router import admin_router
from app.database import engine
from app import models
from app.config import settings
from app.logging_config import setup_logging, get_logger

# Setup logging before anything else
setup_logging(
    log_level=settings.LOG_LEVEL,
    log_to_file=settings.LOG_TO_FILE,
    log_dir=settings.LOG_DIR
)

logger = get_logger(__name__)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Quizentia",
    description="Quiz generation API",
    version="1.0.0"
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Log response
        logger.info(
            f"Response: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Time: {process_time:.3f}s"
        )
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"Request failed: {request.method} {request.url.path} - "
            f"Error: {str(e)} - Time: {process_time:.3f}s",
            exc_info=True
        )
        raise

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception: {request.method} {request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# CORS Config
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(admin_router)

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting Quizentia API in {settings.ENVIRONMENT} mode")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Quizentia API")
