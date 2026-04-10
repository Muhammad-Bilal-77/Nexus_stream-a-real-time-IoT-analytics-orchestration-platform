import os
import subprocess
import getpass

def run(cmd, desc=None):
    """Run shell commands safely with optional description."""
    if desc:
        print(desc)
    subprocess.run(cmd, shell=True, check=True)

print("=====================================================")
print("  NexusStream Local PostgreSQL Configuration Script  ")
print("=====================================================")

# --- Step 1: Read NexusStream Configuration ---
env_path = os.path.join(os.getcwd(), ".env")
db_name = "nexusstream"
db_user = "nexus_admin"
db_user_password = "changeme"

if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("POSTGRES_DB="):
                db_name = line.strip().split("=")[1]
            elif line.startswith("POSTGRES_USER="):
                db_user = line.strip().split("=")[1]
            elif line.startswith("POSTGRES_PASSWORD="):
                db_user_password = line.strip().split("=")[1]
else:
    print("Warning: .env file not found. Using defaults.")

# --- Step 2: User Input ---
print("\nWe are ready to provision the NexusStream Identity and RBAC Database.")
pg_password = getpass.getpass("Enter your local PostgreSQL 'postgres' superuser password (hidden): ")

print(f"\nSetting up PostgreSQL database '{db_name}' and user '{db_user}'...")

# --- Step 3: Detect PostgreSQL executable path ---
# Tries the default path we found in the filesystem scan
pg_path = r'"C:\Program Files\PostgreSQL\18\bin\psql.exe"'
if not os.path.exists(pg_path.replace('"', '')):
    print("PostgreSQL 18 path not found. Checking common paths...")
    # Attempt fallback if they changed versions
    possible_paths = [
        r'"C:\Program Files\PostgreSQL\17\bin\psql.exe"',
        r'"C:\Program Files\PostgreSQL\16\bin\psql.exe"',
        r'"C:\Program Files\PostgreSQL\15\bin\psql.exe"'
    ]
    for p in possible_paths:
        if os.path.exists(p.replace('"', '')):
            pg_path = p
            break
    else:
        print("ERROR: psql.exe not found. Please adjust pg_path in this script manually.")
        exit(1)

# --- Step 4: Create database, user, and grant privileges ---
try:
    os.environ["PGPASSWORD"] = pg_password

    # Create database and user
    # Using '|| echo' or similar error catching could be nice, but standard run check=True is what the user provided
    print(f"Executing: {pg_path} -U postgres -c CREATE DATABASE")
    
    # We use a trick to not fail if database exists. But subprocess.run with check=True will fail if DB already exists.
    # To mimic user's script exactly:
    try:
        run(f'{pg_path} -U postgres -c "CREATE DATABASE {db_name};"', "Creating database...")
    except subprocess.CalledProcessError:
        print("Database might already exist, proceeding...")

    try:
        run(f'{pg_path} -U postgres -c "CREATE USER {db_user} WITH PASSWORD \'{db_user_password}\';"', "Creating user...")
    except subprocess.CalledProcessError:
        print("User might already exist, updating password...")
        run(f'{pg_path} -U postgres -c "ALTER USER {db_user} WITH PASSWORD \'{db_user_password}\';"', "Updating user password...")

    run(f'{pg_path} -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"', "Granting privileges on database...")

    # --- Step 5: Fix schema ownership and run NexusStream initialization ---
    schema_fix_sql = f"""
    \\c {db_name};
    ALTER SCHEMA public OWNER TO {db_user};
    GRANT ALL PRIVILEGES ON SCHEMA public TO {db_user};
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {db_user};
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {db_user};
    """
    with open("schema_fix.sql", "w") as f:
        f.write(schema_fix_sql)

    run(f'{pg_path} -U postgres -f schema_fix.sql', "Fixing schema privileges and ownership...")
    os.remove("schema_fix.sql")

    # NexusStream specific: Load the platform schema!
    init_sql_path = os.path.join(os.getcwd(), "databases", "postgres", "init.sql")
    if os.path.exists(init_sql_path):
        run(f'{pg_path} -U postgres -d {db_name} -f "{init_sql_path}"', "Initializing NexusStream tables and seeding 'admin' user...")
    else:
        print(f"Warning: {init_sql_path} missing. Tables were not populated.")

except Exception as e:
    print(f"Error running PostgreSQL commands: {e}")
    exit(1)

print("\n🚀 PostgreSQL setup is complete.")
print("The 'auth-service' and 'dashboard-service' can now securely connect locally!")
