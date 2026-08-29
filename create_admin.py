import asyncio
from passlib.context import CryptContext
from sqlalchemy.future import select
from database import AsyncSessionLocal
from models.user import User

# Configure the password hashing algorithm
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

async def create_superuser():
    async with AsyncSessionLocal() as session:
        # Check if the admin already exists to prevent duplicates
        result = await session.execute(select(User).where(User.username == "admin_ntro"))
        existing_user = result.scalars().first()
        
        if existing_user:
            print("Admin user already exists.")
            return

        # Create the new admin officer
        admin_user = User(
            username="admin_ntro",
            hashed_password=get_password_hash("supersecure123"), # Hashing the password
            clearance_level="Admin"
        )
        
        session.add(admin_user)
        await session.commit()
        print("Success: Admin user 'admin_ntro' created with hashed password.")

if __name__ == "__main__":
    asyncio.run(create_superuser())