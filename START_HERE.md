# Start here

1. Read the [README](README.md): what the project decides and the headline results.
2. Open the app. The repository ships a verified result snapshot, so nothing needs rebuilding:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
   .\.venv\Scripts\python.exe -m pip install --no-deps -e .
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

   Start on **Decision centre**, then **Next best offer** (pick any customer), then **Policy value**.
3. Open `powerbi/project/Corridor.pbip` in Power BI Desktop and start on the **Command centre** page.
4. For the role this was built for, read [docs/role-coverage.md](docs/role-coverage.md).
5. For how each method was chosen, including what was tried and rejected, read [DECISIONS.md](DECISIONS.md).
