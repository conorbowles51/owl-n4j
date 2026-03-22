# Starting PostgreSQL Database

## Option 1: Using Docker Compose (Recommended)

If you have Docker installed, start PostgreSQL using:

```bash
docker-compose up -d postgres
```

This will start the PostgreSQL container in the background. The database will be available at:
- **Host**: localhost
- **Port**: 5432
- **Database**: owl_db
- **User**: owl_us
- **Password**: owl_pw

## Option 2: Install PostgreSQL Locally

If you don't have Docker, you can install PostgreSQL locally:

### macOS (using Homebrew):
```bash
brew install postgresql@16
brew services start postgresql@16
```

Then create the database and user:
```bash
createdb owl_db
psql owl_db -c "CREATE USER owl_us WITH PASSWORD 'owl_pw';"
psql owl_db -c "GRANT ALL PRIVILEGES ON DATABASE owl_db TO owl_us;"
```

## Verify Connection

After starting PostgreSQL, verify the connection:

```bash
# Test with psql (if installed)
psql -h localhost -U owl_us -d owl_db

# Or test with Python
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://owl_us:owl_pw@localhost:5432/owl_db')
with engine.connect() as conn:
    result = conn.execute(text('SELECT version()'))
    print('Connected!', result.fetchone()[0])
"
```

## Check if PostgreSQL is Running

```bash
# Check Docker container
docker ps | grep owl-pg

# Or check if port is listening
lsof -i :5432
```

## Troubleshooting

1. **Port 5432 already in use**: Another PostgreSQL instance might be running. Stop it or change the port in `docker-compose.yml`.

2. **Connection refused**: Make sure PostgreSQL is actually running and listening on port 5432.

3. **Authentication failed**: Verify the credentials in `.env` match those in `docker-compose.yml`:
   - User: `owl_us`
   - Password: `owl_pw`
   - Database: `owl_db`

4. **DATABASE_URL format**: Should be:
   ```
   DATABASE_URL=postgresql://owl_us:owl_pw@localhost:5432/owl_db
   ```
