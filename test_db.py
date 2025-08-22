import os
from dotenv import load_dotenv
load_dotenv(override=True)

print("=== Testing Database Connection ===")
print(f"PGHOST: {os.getenv('PGHOST')}")
print(f"PGPORT: {os.getenv('PGPORT')}")
print(f"PGDATABASE: {os.getenv('PGDATABASE')}")
print(f"PGUSER: {os.getenv('PGUSER')}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'Not set')}")

# Test database import
try:
    import database
    print(f"Database config in module: {database.DB_CONFIG}")
    result = database.health_check()
    print("Database health check result:", result)
except Exception as e:
    print("Database error:", e)
    import traceback
    traceback.print_exc()
