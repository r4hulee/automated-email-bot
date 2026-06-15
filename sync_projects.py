"""
╔══════════════════════════════════════════════════════════════════╗
║         AUTOMATED BOT  —  sync_projects.py                      ║
║  Fetches your public GitHub repos → builds projects.json         ║
║  → pushes it to the portfolio repo (r4hulee/portfolio)           ║
║  Triggered by: push to main  OR  midnight IST every day          ║
╚══════════════════════════════════════════════════════════════════╝

HOW IT WORKS:
  1. Calls the GitHub API to list all public repos for r4hulee
  2. Extracts: name, description, url, language, topics, homepage
  3. Sorts by most recently updated (newest first)
  4. Saves a local copy of projects.json in this repo
  5. Pushes the updated projects.json to r4hulee/portfolio via GitHub API

SECRETS REQUIRED (set in automated-email-bot repo → Settings → Secrets):
  • PORTFOLIO_PAT  — Personal Access Token with  Contents: Write
                     permission on the  r4hulee/portfolio  repo.

HOW TO CREATE A PORTFOLIO PAT:
  1. GitHub → Profile icon → Settings → Developer settings
  2. Personal access tokens → Fine-grained tokens → Generate new token
  3. Repository access: Only select  r4hulee/portfolio
  4. Permissions → Contents → Read and write
  5. Generate → copy the token → add as secret  PORTFOLIO_PAT

LOCAL TESTING:
  Add to your .env file:
      PORTFOLIO_PAT=your_personal_access_token_here
  Then run:  python sync_projects.py
"""

# ── Standard library imports ───────────────────────────────────────────────────
import os
import json
import base64
from datetime import datetime, timezone

# ── Third-party imports ────────────────────────────────────────────────────────
import requests
from dotenv import load_dotenv

# ── Load .env for local testing ────────────────────────────────────────────────
load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

GITHUB_USERNAME  = "r4hulee"
PORTFOLIO_REPO   = "portfolio"          # The repo that hosts the portfolio site
PORTFOLIO_BRANCH = "main"              # Branch inside the portfolio repo

# Personal Access Token — read from environment (never hardcode!)
PORTFOLIO_PAT = os.environ.get("PORTFOLIO_PAT")

# GitHub API base
GITHUB_API = "https://api.github.com"

# Local filename to save a copy of the generated JSON
LOCAL_JSON_PATH = "projects.json"


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_api_headers():
    """
    Returns request headers for GitHub API calls.
    If PORTFOLIO_PAT is set, it's included for authentication.
    Using a PAT greatly increases the rate limit (5 000 req/hr vs 60 req/hr).
    """
    headers = {
        "Accept"    : "application/vnd.github+json",
        "User-Agent": "automated-bot-sync/1.0",
    }
    if PORTFOLIO_PAT:
        headers["Authorization"] = f"Bearer {PORTFOLIO_PAT}"
    return headers


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — FETCH REPOSITORIES
# ══════════════════════════════════════════════════════════════════════════════

def fetch_public_repos():
    """
    Fetches ALL public repositories for GITHUB_USERNAME from the GitHub API.
    Handles pagination automatically so you get every repo, not just the first 30.

    Returns:
        list — raw repo dicts from the GitHub API (can be empty on failure)
    """
    all_repos = []
    page      = 1

    while True:
        url = (
            f"{GITHUB_API}/users/{GITHUB_USERNAME}/repos"
            f"?type=public"         # Public repos only
            f"&sort=updated"        # Return newest-updated first
            f"&direction=desc"
            f"&per_page=100"        # Max allowed per page
            f"&page={page}"
        )

        print(f"[INFO] Fetching repos page {page}...")
        try:
            resp = requests.get(url, headers=get_api_headers(), timeout=15)

            # ── Rate limit check ──────────────────────────────────────────────
            if resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                reset_ts  = resp.headers.get("X-RateLimit-Reset", "?")
                print(
                    f"[WARNING] GitHub API rate limit hit! "
                    f"Remaining: {remaining}, resets at Unix time {reset_ts}.\n"
                    f"[TIP] Set PORTFOLIO_PAT to get 5 000 requests/hour instead of 60."
                )
                break

            if resp.status_code == 404:
                print(f"[ERROR] GitHub user '{GITHUB_USERNAME}' not found.")
                break

            resp.raise_for_status()   # Raise for any other 4xx / 5xx

            page_data = resp.json()

            # Empty page means we have reached the last page — stop paginating
            if not page_data:
                break

            all_repos.extend(page_data)
            print(f"[INFO] Page {page}: got {len(page_data)} repos")
            page += 1

        except requests.exceptions.ConnectionError:
            print("[ERROR] No internet connection. Cannot fetch repositories.")
            break
        except requests.exceptions.Timeout:
            print("[ERROR] GitHub API timed out.")
            break
        except requests.exceptions.HTTPError as e:
            print(f"[ERROR] GitHub API HTTP error: {e}")
            break

    print(f"[INFO] Total public repos fetched: {len(all_repos)}")
    return all_repos


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — FORMAT & SORT
# ══════════════════════════════════════════════════════════════════════════════

def format_repo(raw):
    """
    Takes one raw repo dict from the GitHub API and returns only the fields
    we want to expose in projects.json. Handles None values safely.

    Fields kept: name, description, url, language, topics, homepage
    (stars, forks, updated_at excluded per user request)

    The internal '_sort_key' is added for sorting and removed before saving.
    """
    return {
        "name"       : raw.get("name", ""),
        "description": raw.get("description") or "",   # None → empty string
        "url"        : raw.get("html_url", ""),
        "language"   : raw.get("language")  or "N/A",
        "topics"     : raw.get("topics", []),          # GitHub topics array
        "homepage"   : raw.get("homepage")  or "",
        # Internal only — used for sorting, stripped before JSON output
        "_sort_key"  : raw.get("updated_at", ""),
    }


def generate_projects_data(raw_repos):
    """
    Formats and sorts the raw repo list.
    Sorting: most recently updated first (using ISO 8601 updated_at string).

    Returns:
        list — cleaned, sorted list of project dicts ready for projects.json
    """
    # Format every repo
    formatted = [format_repo(r) for r in raw_repos]

    # Sort by the internal _sort_key (ISO date strings sort correctly as text)
    formatted.sort(key=lambda r: r["_sort_key"], reverse=True)

    # Remove the internal sort key before saving to JSON
    for project in formatted:
        del project["_sort_key"]

    return formatted


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — SAVE LOCAL COPY
# ══════════════════════════════════════════════════════════════════════════════

def save_local_json(projects):
    """
    Saves a local copy of projects.json in this repo directory.
    Useful for debugging and checking output before it goes to the portfolio.

    Args:
        projects (list): formatted project data
    """
    with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as f:
        # indent=2 makes it human-readable; ensure_ascii=False keeps Unicode chars
        json.dump(projects, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Local copy saved → {LOCAL_JSON_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — PUSH TO PORTFOLIO REPO
# ══════════════════════════════════════════════════════════════════════════════

def get_existing_file_sha():
    """
    Gets the current SHA hash of projects.json in the portfolio repo.
    The GitHub Contents API requires the existing file's SHA when updating a file
    (this prevents accidental overwrites and acts like an optimistic lock).

    Returns:
        str  — SHA hash if file exists
        None — if the file doesn't exist yet (it will be created fresh)
    """
    url = (
        f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{PORTFOLIO_REPO}"
        f"/contents/{LOCAL_JSON_PATH}"
        f"?ref={PORTFOLIO_BRANCH}"
    )

    resp = requests.get(url, headers=get_api_headers(), timeout=10)

    if resp.status_code == 200:
        sha = resp.json().get("sha")
        print(f"[INFO] Existing projects.json found (SHA: {sha[:8]}...)")
        return sha
    elif resp.status_code == 404:
        print("[INFO] projects.json not found in portfolio — will create it fresh.")
        return None
    else:
        print(f"[WARNING] Could not read existing file SHA: {resp.status_code}")
        return None


def push_to_portfolio(projects):
    """
    Pushes the updated projects.json to the r4hulee/portfolio repo using the
    GitHub Contents API (PUT request).

    This does NOT require cloning the repo — it's a direct API call.

    Args:
        projects (list): formatted, sorted list of project dicts

    Returns:
        bool — True if pushed successfully, False otherwise
    """
    if not PORTFOLIO_PAT:
        print(
            "[ERROR] PORTFOLIO_PAT is not set.\n"
            "[TIP]  Add it as a GitHub Secret in automated-email-bot:\n"
            "         Repo → Settings → Secrets → Actions → New secret\n"
            "         Name: PORTFOLIO_PAT\n"
            "         Value: your Personal Access Token"
        )
        return False

    # ── Build the JSON content ────────────────────────────────────────────────
    json_str = json.dumps(projects, indent=2, ensure_ascii=False)

    # GitHub API requires the file content to be Base64 encoded
    encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    # ── Get existing SHA (required to update an existing file) ────────────────
    existing_sha = get_existing_file_sha()

    # ── Build the commit message ───────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit_msg = f"🤖 Auto-sync: {len(projects)} projects [{now_utc}]"

    # ── Prepare API payload ────────────────────────────────────────────────────
    payload = {
        "message": commit_msg,
        "content": encoded,
        "branch" : PORTFOLIO_BRANCH,
    }

    # Include the SHA only when updating an existing file
    if existing_sha:
        payload["sha"] = existing_sha

    # ── Make the PUT request ───────────────────────────────────────────────────
    url = (
        f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{PORTFOLIO_REPO}"
        f"/contents/{LOCAL_JSON_PATH}"
    )

    print(f"[INFO] Pushing to {GITHUB_USERNAME}/{PORTFOLIO_REPO}/{LOCAL_JSON_PATH}...")
    resp = requests.put(url, headers=get_api_headers(), json=payload, timeout=20)

    if resp.status_code in (200, 201):
        action = "Updated" if existing_sha else "Created"
        commit_url = resp.json().get("commit", {}).get("html_url", "")
        print(f"[INFO] ✅ projects.json {action} in portfolio repo!")
        if commit_url:
            print(f"[INFO] Commit: {commit_url}")
        return True
    else:
        print(f"[ERROR] Failed to push — HTTP {resp.status_code}")
        print(f"[ERROR] Response: {resp.text[:300]}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Runs the full sync pipeline:
      Step 1 → Fetch repos from GitHub API
      Step 2 → Format + sort the data
      Step 3 → Save a local copy
      Step 4 → Push to portfolio repo
    """
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("╔══════════════════════════════════════════╗")
    print("║   🔄  GitHub Sync  —  Starting...        ║")
    print(f"║   🕐  {run_time}                  ║")
    print(f"║   👤  {GITHUB_USERNAME:<34}║")
    print(f"║   📦  {GITHUB_USERNAME}/{PORTFOLIO_REPO:<25}║")
    print("╚══════════════════════════════════════════╝\n")

    # Step 1
    print("[STEP 1/4] Fetching public repositories...")
    raw_repos = fetch_public_repos()

    if not raw_repos:
        print("[WARNING] No repositories returned. Aborting.")
        raise SystemExit(1)

    # Step 2
    print("\n[STEP 2/4] Formatting and sorting data...")
    projects = generate_projects_data(raw_repos)
    print(f"[INFO] Processed {len(projects)} repositories.")

    # Step 3
    print("\n[STEP 3/4] Saving local copy...")
    save_local_json(projects)

    # Step 4
    print("\n[STEP 4/4] Pushing to portfolio repo...")
    success = push_to_portfolio(projects)

    print()
    if success:
        print("✅ GitHub sync completed successfully!\n")
    else:
        print("❌ Sync failed — see errors above.\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
