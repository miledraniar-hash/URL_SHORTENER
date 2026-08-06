from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models.url import URL, Base
from services.url_service import generate_short_code

import validators

app = FastAPI()

# Create tables
Base.metadata.create_all(bind=engine)


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create short URL
@app.post("/api/shorten")
def shorten_url(original_url: str, db: Session = Depends(get_db)):

    existing_url = db.query(URL).filter(
    URL.original_url == original_url
    ).first()

    if existing_url:
        return {
        "short_code": existing_url.short_code

    }

    # 1. Create URL object first
    new_url = URL(
        original_url=original_url,
        short_code="TEMP"
    )

    db.add(new_url)
    db.flush()  # get generated ID

    # 2. Generate Base62 code using ID
    short_code = generate_short_code(new_url.id)

    # 3. Update short code
    new_url.short_code = short_code

    # 4. Validation URL
    if not validators.url(original_url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL"
        )
    
    # Save changes
    db.commit()
    db.refresh(new_url)

    return {
        "short_code": new_url.short_code
    }


# Redirect short URL
@app.get("/{short_code}")
def redirect_url(short_code: str, db: Session = Depends(get_db)):

    url = db.query(URL).filter(
        URL.short_code == short_code
    ).first()

    if not url:
        raise HTTPException(
            status_code=404,
            detail="URL not found"
        )

    return RedirectResponse(
        url=url.original_url
    )