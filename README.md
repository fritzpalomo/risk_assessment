# PhilPEN Risk Records (Streamlit)

A data-entry app for PhilPEN risk factors taken from PhilHealth Konsulta Annex 5 forms. It has 33 fields you type and 11 it calculates. Records are stored in `records.db` (SQLite), and **Export CSV** produces the file for the explainable ML dashboard.

Files: `app.py`, `fields.json` (the field list), `requirements.txt`.

## 1. Run it on your computer

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. Records are saved in `records.db` next to `app.py`.

## 2. Publish on Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py`, `fields.json`, `requirements.txt` and `.gitignore`. Do not upload `records.db`.
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, then **Deploy a public app from GitHub**.
4. Pick your repository and branch, and set **Main file path** to `app.py`.
5. Click **Deploy**. You get a link like `https://<name>.streamlit.app`.
6. Make it private: open the app's **Settings → Sharing** and allow only the email addresses you choose. Community Cloud allows one private app per account.

## Important: saved records on Streamlit Cloud

Streamlit Community Cloud does not keep files permanently. `records.db` is erased whenever the app restarts, goes to sleep after a few days without visitors, or is redeployed. To stay safe:

- **Export CSV after every encoding session**, or
- run the app on your own computer (step 1), where `records.db` stays, or
- switch storage to an online database such as Google Sheets or Supabase, which keeps records permanently.
