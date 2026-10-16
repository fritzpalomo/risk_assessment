# PhilPEN Risk Records (Streamlit)

A data-entry app for PhilPEN risk factors taken from PhilHealth Konsulta Annex 5 forms. It has 33 fields you type and 11 it calculates. Each record gets an automatic patient code (P-0001, P-0002, ...). Records are stored in `records.db` (SQLite), and **Export CSV** produces the file for the explainable ML dashboard.

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

## 3. Keep records permanently with Google Sheets (recommended)

Streamlit Community Cloud erases `records.db` whenever the app restarts or sleeps. Connect a Google Sheet and every record is saved there instead.

1. **Create the sheet.** In Google Sheets, create a blank spreadsheet named, for example, *PhilPEN Records*, and copy its URL.
2. **Create a service account** (a robot Google account the app signs in with):
   1. Open https://console.cloud.google.com, then create a project (any name).
   2. Search for **Google Sheets API** and click **Enable**.
   3. Go to **IAM & Admin → Service Accounts → Create service account**, give it a name, and click **Done**.
   4. Open the new service account, go to **Keys → Add key → Create new key → JSON**. A `.json` file downloads.
3. **Share the sheet** with the service account's email (it looks like `name@project.iam.gserviceaccount.com`) as **Editor**.
4. **Add the secrets in Streamlit.** On share.streamlit.io, open your app's **⋮ → Settings → Secrets** and paste the following, filling in the values from the `.json` file:

```toml
sheet_url = "https://docs.google.com/spreadsheets/d/..."

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

5. Save. The app restarts, and the yellow "saved on this server only" warning disappears. Each record becomes one row in the sheet.

Never upload the `.json` key file to GitHub.

## Restoring records

On the **Records** tab, open **Import records from an exported CSV** and upload any CSV you exported from this app. Records that are already saved are skipped, so importing the same file twice is safe.

## Important: saved records on Streamlit Cloud

Streamlit Community Cloud does not keep files permanently. `records.db` is erased whenever the app restarts, goes to sleep after a few days without visitors, or is redeployed. To stay safe:

- **Export CSV after every encoding session**, or
- run the app on your own computer (step 1), where `records.db` stays, or
- switch storage to an online database such as Google Sheets or Supabase, which keeps records permanently.
