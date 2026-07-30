# ─── Vivacity Auth Routes ─────────────────────────────────────────────────────
from fastapi import APIRouter, HTTPException, Header, Depends
import db

router = APIRouter(prefix="/auth", tags=["auth"])

async def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(" ")[1]
    try:
        # Verify the token against Supabase
        res = db.get_supabase().auth.get_user(token)
        if not res or not res.user:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = res.user.id
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    # Get user profile from our public users table
    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User profile not found")
        
    return user

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
