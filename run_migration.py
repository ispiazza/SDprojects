#!/usr/bin/env python3
"""
Simple migration using the working database.py module
Handles PostgreSQL functions with $$ properly
"""
import database
import re

print("🚀 Starting Database Migration")
print("=" * 50)

# Test connection
print("\n🔌 Testing connection...")
result = database.test_connection()
if not result['success']:
    print(f"❌ Connection failed: {result['error']}")
    exit(1)

print(f"✅ Connected to: {result['database']}")
print(f"   Host: {result['host']}")
print(f"   User: {result['user']}")

# Read schema
print("\n📊 Running schema migration...")
with open('migrations/schema.sql', 'r') as f:
    schema_sql = f.read()

def parse_sql_statements(sql):
    """
    Parse SQL statements properly, respecting $$ delimiters
    """
    statements = []
    current_statement = []
    in_dollar_quote = False
    
    lines = sql.split('\n')
    
    for line in lines:
        # Skip comments
        if line.strip().startswith('--'):
            continue
            
        # Check for $$ delimiters
        if '$$' in line:
            in_dollar_quote = not in_dollar_quote
        
        current_statement.append(line)
        
        # If we hit a semicolon and we're not in a dollar quote, end statement
        if ';' in line and not in_dollar_quote:
            stmt = '\n'.join(current_statement).strip()
            if stmt and stmt != ';':
                statements.append(stmt)
            current_statement = []
    
    # Add any remaining statement
    if current_statement:
        stmt = '\n'.join(current_statement).strip()
        if stmt:
            statements.append(stmt)
    
    return statements

try:
    statements = parse_sql_statements(schema_sql)
    print(f"Found {len(statements)} SQL statements to execute")
    
    with database.get_db_cursor() as (cursor, conn):
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for i, statement in enumerate(statements, 1):
            try:
                cursor.execute(statement)
                conn.commit()
                print(f"  ✅ Statement {i}/{len(statements)}")
                success_count += 1
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "duplicate" in error_msg:
                    print(f"  ⚠️  Statement {i}: Already exists (skipping)")
                    conn.rollback()  # Rollback and continue
                    skip_count += 1
                else:
                    print(f"  ❌ Statement {i} failed: {e}")
                    # Show first 100 chars of failed statement
                    stmt_preview = statement[:100].replace('\n', ' ')
                    print(f"     Statement: {stmt_preview}...")
                    conn.rollback()  # Rollback and continue
                    error_count += 1
        
        print(f"\n📊 Migration Summary:")
        print(f"   ✅ Successful: {success_count}")
        print(f"   ⚠️  Skipped: {skip_count}")
        print(f"   ❌ Errors: {error_count}")
        
        # Verify tables were created
        print("\n🔍 Verifying database...")
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        tables = [row['table_name'] for row in cursor.fetchall()]
        
        if tables:
            print(f"   Tables created: {', '.join(tables)}")
            
            # Check collections
            try:
                cursor.execute("SELECT COUNT(*) FROM collections")
                result = cursor.fetchone()
                collections_count = result['count']
                print(f"   Collections: {collections_count}")
                
                cursor.execute("SELECT name FROM collections")
                collection_names = [row['name'] for row in cursor.fetchall()]
                print(f"   Collection names: {', '.join(collection_names)}")
            except:
                print("   Collections table not yet populated")
            
            # Check records
            try:
                cursor.execute("SELECT COUNT(*) FROM dublin_core_records")
                result = cursor.fetchone()
                records_count = result['count']
                print(f"   Records: {records_count}")
            except:
                print("   Records table not yet populated")
        else:
            print("   ⚠️  No tables found")
        
        print("\n🎉 Migration completed!")
        
except Exception as e:
    print(f"\n❌ Migration failed: {e}")
    import traceback
    traceback.print_exc()