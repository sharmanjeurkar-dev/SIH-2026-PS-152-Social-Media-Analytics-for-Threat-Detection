import os
import jwt
from jwt import PyJWKClient
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("Critical Security Error: SUPABASE URL/ANON_KEY variables are missing!")

jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url, headers={"apikey": SUPABASE_ANON_KEY})

security = HTTPBearer()
router = APIRouter()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate Supabase credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        print(f"DEBUG: Token algorithm detected as: {alg}")
        
        if alg == "HS256":
            if not SUPABASE_JWT_SECRET:
                raise ValueError("HS256 token detected but SUPABASE_JWT_SECRET is missing from .env")
            payload = jwt.decode(
                token, 
                SUPABASE_JWT_SECRET, 
                algorithms=["HS256"], 
                audience="authenticated"
            )
        else:
            # Dynamically handle ES256, RS256, or any modern JWKS-backed algorithm
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token, 
                signing_key.key, 
                algorithms=[alg], 
                audience="authenticated"
            )
            
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        return payload 
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Supabase token has expired"
        )
    except Exception as e:
        print(f"DEBUG: JWT Validation Error: {str(e)}")
        raise credentials_exception