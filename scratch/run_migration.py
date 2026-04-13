import asyncio
import asyncpg
import os
import sys
from pathlib import Path

# Add project root to sys.path to import settings if needed
# But we'll just read DATABASE_URL from environment for simplicity
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable is not set.")
    sys.exit(1)

MIGRATION_FILE = Path(__file__).parent.parent / "migrations" / "003_subscriptions.sql"

async def run_migration():
    print(f"🚀 Connecting to database...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print(f"📂 Reading migration file: {MIGRATION_FILE}")
        
        with open(MIGRATION_FILE, "r") as f:
            sql = f.read()
            
        print("⚡ Executing SQL migration...")
        # asyncpg's execute() can handle multiple statements separated by semicolons
        await conn.execute(sql)
        
        print("✅ Migration successful!")
        await conn.close()
    except Exception as e:
        print(f"❌ ERROR: Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_migration())
