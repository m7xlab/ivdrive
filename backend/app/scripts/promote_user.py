import asyncio
import argparse
import sys
import os

# Ensure the app can be imported
sys.path.append(os.getcwd())

from sqlalchemy import select
from app.database import async_session
from app.models.user import User

async def promote_user(email: str):
    """Promote a user to superuser status."""
    try:
        async with async_session() as session:
            # Import models to ensure they are registered
            
            try:
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()
                
                if not user:
                    print(f"Error: User with email '{email}' not found. Please register via the UI first.")
                    return

                if user.is_superuser:
                    print(f"User '{email}' is already a superuser.")
                    return

                user.is_superuser = True
                await session.commit()
                print(f"Success: User '{email}' has been promoted to superuser!")
            except Exception as e:
                await session.rollback()
                print(f"Database error during promotion: {e}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote an iVDrive user to superuser status.")
    parser.add_argument("--email", required=True, help="Email of the user to promote")
    args = parser.parse_args()
    
    asyncio.run(promote_user(args.email))
