from fastapi import FastAPI, Depends, HTTPException,Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from database import engine, SessionLocal
from models.url import URL, Base
from services.url_service import generate_short_code

import validators

app = FastAPI()
# templates
templates = Jinja2Templates(directory="templates")

# fichiers statiques (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create tables
Base.metadata.create_all(bind=engine)


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Shared logic: validate, dedupe, create, save
def create_short_url(original_url: str, db: Session) -> URL:
    # 1. Validate URL FIRST, before touching the database
    if not validators.url(original_url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL"
        )

    # 2. Reuse existing short code if this exact URL was already shortened
    existing_url = db.query(URL).filter(
        URL.original_url == original_url
    ).first()

    if existing_url:
        return existing_url

    # 3. Create URL object first
    new_url = URL(
        original_url=original_url,
        short_code="TEMP"
    )

    db.add(new_url)
    db.flush()  # get generated ID

    # 4. Generate Base62 code using ID
    new_url.short_code = generate_short_code(new_url.id)

    # 5. Save changes
    db.commit()
    db.refresh(new_url)

    return new_url


# JSON API
@app.post("/api/shorten")
def shorten_url(original_url: str, db: Session = Depends(get_db)):
    new_url = create_short_url(original_url, db)
    return {
        "short_code": new_url.short_code
    }


# HTML form target (used by the homepage form)
@app.post("/shorten", response_class=HTMLResponse)
def shorten_form(
    request: Request,
    original_url: str = Form(...),
    db: Session = Depends(get_db)
):
    new_url = create_short_url(original_url, db)
    short_url = f"{request.base_url}{new_url.short_code}"
    return templates.TemplateResponse(
        request,
        "index.html",
        {"short_url": short_url}
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


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



