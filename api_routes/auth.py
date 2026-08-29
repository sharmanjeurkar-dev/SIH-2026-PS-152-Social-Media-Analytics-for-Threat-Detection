from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from passlib.context import CryptContext

from database import get_db
from models.user import User

router = APIRouter()

# Security configuration (in a real app, hide the secret key in a .env file)
SECRET_KEY = "ntro_super_secret_key_v1"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Query the database for the user
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    
    # 2. Verify the user exists and the password matches the hash
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Generate the JWT with the user's clearance level inside the payload
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "clearance": user.clearance_level},
        expires_delta=access_token_expires
    )
    
    # FastAPI expects exactly this JSON structure for OAuth2 compatibility
    return {"access_token": access_token, "token_type": "bearer"}