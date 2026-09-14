
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import SessionLocal,engine
import database_models
from fastapi.staticfiles import StaticFiles
from routers import auth, courses, enquiries, settings,enrollments


app=FastAPI()

# Configurable CORS
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = [origin.strip() for origin in allowed_origins_env.split(",")] if allowed_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



database_models.Base.metadata.create_all(bind=engine)

# Auto-migrate phone column in users table and parents_phone in enquiries table
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR;"))
        conn.execute(text("ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS parents_phone VARCHAR;"))
        conn.commit()
except Exception as e:
    print(f"Migration note: {e}")



# serve uploaded course images
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads",StaticFiles(directory="uploads"),name="uploads")




# included routers

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(enquiries.router)
app.include_router(settings.router)
app.include_router(enrollments.router)






@app.get('/')
 
def greet():
    # db=SessionLocal()
    return {"message":"welcome to server"}





@app.get("/test-db")
def test_db():
    db = SessionLocal()

    try:
        db.execute(text("SELECT 1"))
        return {"message": "Database connected successfully"}
    finally:
        db.close()
        
        
        
        
        
        
        

 #  APi for testing image upload to 


@app.get("/test-spaces")
def test_spaces():
    from utils.spaces import spaces_client, SPACES_BUCKET

    try:
        spaces_client.head_bucket(
            Bucket=SPACES_BUCKET
        )

        return {
            "message": "DigitalOcean Spaces connected successfully"
        }

    except Exception as e:
        return {
            "error": str(e)
        }