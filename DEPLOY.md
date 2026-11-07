# PlantPulse: make the live site keep its data (step by step)

The Streamlit Cloud server forgets files whenever the app restarts or you push a new version. So the app can keep its data in a hosted
PostgreSQL database instead. Nothing changes on your laptop: without a database address, PlantPulse still uses the local file.

## What YOU do (about 30 minutes)

### A. Update your project folder
1. Extract the new zip into your project folder and replace the files. Keep your own `.git` folder.
2. Open the folder in a terminal and activate your environment (`venv\Scripts\activate`), then run: `pip install -r requirements.txt`
3. Run `run_tests` (double-click). All tests must pass.

### B. Make sure no database or secret is in GitHub
1. In the terminal: `git ls-files | findstr /i ".db secrets"`
2. If it lists a `.db` file: `git rm --cached data/plantpulse.db` (use the path it showed). The new `.gitignore` then keeps it out.
3. Never create `.streamlit/secrets.toml` inside a folder you push without it being ignored (the new `.gitignore` already ignores it).

### C. Create the free hosted database (Neon is the simplest)
1. Sign up at neon.tech and create a project (any name). Choose an AWS region in the **US**: Streamlit's servers are in the US, so the app and the database should be close to each other, not close to you.
2. On the project page click **Connect** and copy the **connection string**. It looks like `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`.
3. Treat it like a password. Do not paste it into chat, screenshots, GitHub, or a file you push.

### D. Test it from your computer (recommended)
1. Create the file `.streamlit/secrets.toml` (it is ignored by git) with one line: `DATABASE_URL = "your connection string"`
2. Run `python check_database.py`. You want: `Storage: PostgreSQL` and `OK: connected ...`.
3. Run `run_app`. The sidebar should say `Storage: PostgreSQL`. Create a test account, close the app, open it again: the account is still there.

### E. Give the address to the live site
1. In Streamlit Cloud open your app, then **Manage app**, then **Settings**, then **Secrets**.
2. Paste the same one line: `DATABASE_URL = "your connection string"` and save.
3. Push the new code: `git add .`, `git commit -m "Hosted database and security"`, `git push`. The app redeploys by itself.

### F. Check the live site
1. The sidebar says `Storage: PostgreSQL` (not "temporary").
2. Create an account, add equipment, then **Manage app**, then **Reboot app**. Log in again: your data is still there.
3. Enter a wrong password 5 times for a test account: it locks for 15 minutes.
4. On the **Account** page, delete a test account: it works and you are logged out.
5. Dates in notes and reports show today's date in Pakistan.

## If something goes wrong
- `The database is not reachable right now`: the address or password in Secrets is wrong, or the database is paused. Open the Neon dashboard, copy the string again.
- The sidebar still says `SQLite file (temporary)`: the Secrets line is missing, misspelled (it must be exactly `DATABASE_URL`), or the app was not rebooted.
- If you ever pasted the connection string somewhere public, reset the database password in Neon and update Secrets.

## What this does NOT do
It is safer, not a security audit. Anyone can still create an account. The team can technically read the database. The free database plans have size and backup limits.
