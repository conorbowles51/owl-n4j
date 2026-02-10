# Fixing Docker Command Not Found on macOS

Docker Desktop is installed but the `docker` command isn't found. Here's how to fix it:

## Quick Fix (Recommended)

1. **Restart your terminal** - Close and reopen your terminal app. Docker Desktop should have added docker to PATH, but your current shell session might not have picked it up.

2. **Verify Docker Desktop is running**:
   - Check the Docker icon in your menu bar (top right)
   - It should show "Docker Desktop is running"

3. **Test the command**:
   ```bash
   docker --version
   docker-compose --version
   ```

## If Restarting Doesn't Work

### Option 1: Check Docker Desktop Settings

1. Open Docker Desktop
2. Go to **Settings** (gear icon) → **General**
3. Make sure **"Use Docker Compose V2"** is checked (if using newer versions)
4. Go to **Settings** → **Resources** → **WSL Integration** (if applicable)
5. Restart Docker Desktop

### Option 2: Manually Add Docker to PATH

Docker Desktop typically installs the CLI tools at:
- `/usr/local/bin/docker` (symlink)
- Or via Docker Desktop's internal path

Add to your `~/.zshrc` (since you're using zsh):

```bash
# Add Docker to PATH
export PATH="/usr/local/bin:$PATH"

# Or if Docker Desktop uses a different location:
# export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Then reload:
```bash
source ~/.zshrc
```

### Option 3: Use Full Path (Temporary)

If you need to use docker immediately, you can use the full path:

```bash
# For docker
/usr/local/bin/docker --version

# For docker-compose (might be docker compose on newer versions)
/usr/local/bin/docker compose version
# or
docker-compose --version
```

## Verify Installation

After fixing, test with:

```bash
# Check docker
docker --version
# Should show: Docker version 24.x.x or similar

# Check docker-compose
docker-compose --version
# Or on newer versions:
docker compose version

# Test connection
docker ps
# Should show running containers (or empty list if none running)
```

## Start PostgreSQL

Once docker is working:

```bash
cd /Users/neilbyrne/Documents/Owl/owl-n4j
docker-compose up -d postgres
```

Or if using newer Docker Compose V2:
```bash
docker compose up -d postgres
```

## Still Not Working?

1. **Reinstall Docker Desktop** - Sometimes a fresh install fixes PATH issues
2. **Check if docker is actually installed**:
   ```bash
   ls -la /usr/local/bin/docker
   ls -la /Applications/Docker.app/Contents/Resources/bin/docker
   ```
3. **Check Docker Desktop logs** - Look for any errors in Docker Desktop's logs
