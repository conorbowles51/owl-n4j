# Fix Docker Credential Helper Error

You're getting this error:
```
error getting credentials - err: exec: "docker-credential-desktop": executable file not found in $PATH
```

## Solution 1: Add Docker Desktop to PATH (Recommended)

Add Docker Desktop's bin directory to your PATH. Edit your `~/.zshrc` file:

```bash
# Open in your editor
nano ~/.zshrc
# or
code ~/.zshrc
```

Add this line at the end:
```bash
# Docker Desktop
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Then reload:
```bash
source ~/.zshrc
```

## Solution 2: Remove Credential Helper (Quick Fix)

If you're only using local Docker (not Docker Hub), you can remove the credential helper:

1. Check your Docker config:
   ```bash
   cat ~/.docker/config.json
   ```

2. If it contains `"credsStore": "desktop"`, edit the file:
   ```bash
   nano ~/.docker/config.json
   ```

3. Remove or comment out the `credsStore` line:
   ```json
   {
     "auths": {},
     "credsStore": ""
   }
   ```
   Or just remove the `credsStore` line entirely.

4. Save and try again:
   ```bash
   docker compose up -d postgres
   ```

## Solution 3: Create Symlink (Alternative)

If the credential helper exists but isn't in PATH:

```bash
# Find where it is
find /Applications/Docker.app -name "docker-credential-desktop" 2>/dev/null

# Create symlink (if found, replace /path/to with actual path)
sudo ln -s /Applications/Docker.app/Contents/Resources/bin/docker-credential-desktop /usr/local/bin/docker-credential-desktop
```

## Verify Fix

After applying a solution, test:

```bash
# Check if credential helper is found
which docker-credential-desktop

# Try pulling an image (this will test credentials)
docker pull hello-world

# Start PostgreSQL
cd /Users/neilbyrne/Documents/Owl/owl-n4j
docker compose up -d postgres
```

## Quick Test (No Credentials Needed)

If you just need to start PostgreSQL and don't need Docker Hub authentication, you can temporarily work around this:

```bash
# Set empty credential store for this session
export DOCKER_CONFIG=~/.docker
mkdir -p ~/.docker
echo '{}' > ~/.docker/config.json

# Then try
docker compose up -d postgres
```

The postgres:16 image should pull fine since it's a public image.
