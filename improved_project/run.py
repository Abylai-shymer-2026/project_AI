# run.py
import asyncio
from dotenv import load_dotenv

# Load .env as early as possible
load_dotenv()

from app.bot import main

if __name__ == "__main__":
    asyncio.run(main())