"""PhilPEN Risk Records: encode PhilPEN risk factors from Annex 5 forms (Streamlit)."""
import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).parent
FIELDS = json.loads((HERE / "fields.json").read_text(encoding="utf-8"))
DB_PATH = HERE / "records.db"

st.set_page_config(page_title="PhilPEN Risk Records", page_icon="🩺", layout="wide")


# ---------- storage ----------
# Records go to a Google Sheet when the app has Google credentials in its secrets
# (permanent), otherwise to records.db next to app.py (erased on Streamlit Cloud restarts).
SHEET_HEADER = ["id", "encoded_at", "updated_at", "data"]


def use_sheets():
    try:
        return "gcp_service_account" in st.secrets and "sheet_url" in st.secrets
    except Exception:
        return False


@st.cache_resource
def get_sheet():
    import gspread
    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    ws = gc.open_by_url(st.secrets["sheet_url"]).sheet1
    if ws.row_values(1) != SHEET_HEADER:
        ws.update([SHEET_HEADER], "A1:D1")
    return ws


@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, encoded_at TEXT, updated_at TEXT, data TEXT)"
    )
    return conn


def load_records():
    if use_sheets():
        rows = [(r["id"], r["encoded_at"], r["updated_at"], r["data"])
                for r in get_sheet().get_all_records(expected_headers=SHEET_HEADER) if r.get("id")]
    else:
        rows = get_conn().execute("SELECT id, encoded_at, updated_at, data FROM records").fetchall()
    recs = [{"id": str(r[0]), "encoded_at": str(r[1]), "updated_at": str(r[2]), "values": json.loads(r[3])} for r in rows]
    return sorted(recs, key=lambda r: r["updated_at"], reverse=True)


def save_record(rec_id, values, encoded_at, updated_at=None):
    now = datetime.now().isoformat(timespec="seconds")
    row = [rec_id, encoded_at or now, updated_at or now, json.dumps(values)]
    if use_sheets():
        ws = get_sheet()
        cell = ws.find(rec_id, in_column=1)
        if cell:
            ws.update([row], f"A{cell.row}:D{cell.row}")
        else:
            ws.append_row(row, value_input_option="RAW")
    else:
        get_conn().execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)", row)
        get_conn().commit()


def delete_record(rec_id):
    if use_sheets():
        ws = get_sheet()
        cell = ws.find(rec_id, in_column=1)
        if cell:
            ws.delete_rows(cell.row)
    else:
        get_conn().execute("DELETE FROM records WHERE id = ?", (rec_id,))
        get_conn().commit()


def import_csv(file, existing):
    """Add records from an exported CSV; records whose id is already saved are skipped."""
    df = pd.read_csv(file, dtype=str, keep_default_na=False)
    known = {r["id"] for r in existing}
    types = {f["v"]: f["t"] for f in FIELDS}
    added = 0
    for _, row in df.iterrows():
        rec_id = row.get("record_id") or uuid.uuid4().hex[:12]
        if rec_id in known:
            continue
        v = {}
        for col, val in row.items():
            if col in types and types[col] not in ("calc",) and val != "":
                v[col] = float(val) if types[col] == "number" else val
        v.update(derive(v))
        save_record(rec_id, v, row.get("encoded_at") or None, row.get("updated_at") or None)
        known.add(rec_id)
        added += 1
    return added


def next_patient_code(records):
    nums = [int(m.group(1)) for r in records
            if (m := re.fullmatch(r"P-(\d+)", str(r["values"].get("patient_code", ""))))]
    return f"P-{max(nums, default=0) + 1:04d}"


# ---------- calculated fields (DOH PhilPEN manual cut-offs) ----------
def derive(v):
    d = {}
    yn = lambda b: "Yes" if b else "No"
    h, w = v.get("height_cm"), v.get("weight_kg")
    if h and w:
        d["bmi"] = round(w / (h / 100) ** 2, 1)
        b = d["bmi"]
        d["bmi_class"] = ("Underweight" if b <= 18.5 else "Healthy" if b < 23 else
                          "At risk" if b < 25 else "Obese I" if b < 30 else "Obese II")
    sbp, dbp = v.get("sbp"), v.get("dbp")
    if sbp and dbp:
        cs = 3 if sbp >= 160 else 2 if sbp >= 140 else 1 if sbp >= 120 else 0
        cd = 3 if dbp >= 100 else 2 if dbp >= 90 else 1 if dbp >= 80 else 0
        d["bp_class"] = ["Normal", "Pre-hypertension", "Stage 1 hypertension", "Stage 2 hypertension"][max(cs, cd)]
    if v.get("blood_sugar") and v.get("blood_sugar_test"):
        d["raised_blood_sugar"] = yn(v["blood_sugar"] >= (126 if v["blood_sugar_test"] == "FBS" else 200))
    if v.get("total_cholesterol"):
        d["total_cholesterol_mmol"] = round(v["total_cholesterol"] / 38, 2)
        d["raised_cholesterol"] = yn(v["total_cholesterol"] >= 200)
    aq = [v.get(f"angina_q{i}") for i in (3, 4, 5, 6, 7)]
    if all(aq):
        d["angina_heart_attack"] = yn(all(x == "Yes" for x in aq))
    elif "No" in aq:
        d["angina_heart_attack"] = "No"
    if v.get("stroke_q8"):
        d["stroke_tia"] = v["stroke_q8"]
    if v.get("smoking"):
        d["smoker_for_risk"] = yn(v["smoking"] == "Yes")
    if v.get("dm_diagnosed") or d.get("raised_blood_sugar"):
        d["diabetes_for_risk"] = yn(v.get("dm_diagnosed") == "Yes" or d.get("raised_blood_sugar") == "Yes")
    if v.get("age") is not None:
        d["needs_screening"] = yn(
            v["age"] > 40
            or d.get("smoker_for_risk") == "Yes"
            or (sbp or 0) >= 120 or (dbp or 0) >= 80
            or d.get("diabetes_for_risk") == "Yes"
            or "Yes" in [v.get(k) for k in ("fh_hypertension", "fh_stroke", "fh_heart_attack", "fh_diabetes")]
        )
    return d


# ---------- form ----------
def key(var):
    # The form version is part of every widget key, so bumping it gives a brand-new blank form.
    return f"f_{var}_{st.session_state.get('form_ver', 0)}"


def clear_form():
    for f in FIELDS:
        st.session_state.pop(key(f["v"]), None)
    st.session_state.form_ver = st.session_state.get("form_ver", 0) + 1
    st.session_state.editing = None


def load_into_form(rec):
    clear_form()
    for f in FIELDS:
        if f["t"] not in ("calc", "auto") and f["v"] in rec["values"]:
            st.session_state[key(f["v"])] = rec["values"][f["v"]]
    st.session_state.editing = rec


def read_form():
    v = {}
    for f in FIELDS:
        if f["t"] in ("calc", "auto"):
            continue
        val = st.session_state.get(key(f["v"]))
        if isinstance(val, str):
            val = val.strip()
        if val not in (None, ""):
            v[f["v"]] = val
    v.update(derive(v))
    return v


def render_field(f, current):
    label = f["l"] + (f" ({f['u']})" if f["u"] and f["t"] == "number" else "")
    help_ = f["n"] or None
    if f["t"] == "auto":
        st.text_input(label + " · automatic", value=current.get(f["v"], ""), disabled=True, help=help_)
    elif f["t"] == "calc":
        st.text_input(label + " · calculated", value=str(current.get(f["v"], "")), disabled=True,
                      help=help_)
    elif f["t"] == "choice":
        if len(f["o"]) <= 3:
            st.radio(label, f["o"], index=None, horizontal=True, key=key(f["v"]), help=help_)
        else:
            st.selectbox(label, f["o"], index=None, placeholder="Choose", key=key(f["v"]), help=help_)
    elif f["t"] == "number":
        st.number_input(label, min_value=0.0, value=None, step=1.0, format="%g", key=key(f["v"]), help=help_)
    else:
        st.text_input(label, key=key(f["v"]), help=help_)


def section_fields():
    groups = {}
    for f in FIELDS:
        groups.setdefault(f["s"], []).append(f)
    return groups


# ---------- pages ----------
if "editing" not in st.session_state:
    st.session_state.editing = None

records = load_records()

st.title("PhilPEN Risk Records")
st.caption("Encode the PhilPEN risk factors from each Annex 5 form. Records are anonymous: "
           "each record gets an automatic patient code (P-0001, P-0002, ...). Each saved form becomes one row in the CSV export.")
if not use_sheets():
    st.warning("Records are saved on this server only. Streamlit Cloud erases them when the app restarts, "
               "so export the CSV after each session, or connect a Google Sheet for permanent storage (see README).")

top = st.columns([2, 2, 2, 4])
top[0].metric("Number of records", len(records))
cols = ["record_id", "encoded_at", "updated_at"] + [f["v"] for f in FIELDS]
df = pd.DataFrame([{"record_id": r["id"], "encoded_at": r["encoded_at"], "updated_at": r["updated_at"],
                    **r["values"]} for r in records], columns=cols)
csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
csv_name = f"philpen_risk_records_{datetime.now():%Y-%m-%d}.csv"
top[1].download_button("Export CSV", csv_bytes, file_name=csv_name, mime="text/csv", width="stretch",
                       disabled=not records, help=None if records else "Save a record first",
                       key="export_top")
if top[2].button("New record", type="primary", width="stretch"):
    clear_form()
    st.rerun()

tab_form, tab_list = st.tabs(["Encode form", "Records"])

with tab_list:
    with st.expander("Import records from an exported CSV"):
        up = st.file_uploader("CSV exported from this app", type="csv", key="import_csv")
        if up is not None and st.button("Import records"):
            n = import_csv(up, records)
            st.session_state.import_msg = f"Imported {n} record(s). Records already saved were skipped."
            st.rerun()
        if st.session_state.get("import_msg"):
            st.success(st.session_state.pop("import_msg"))
    if not records:
        st.info("No records yet. Use the Encode form tab to save the first one.")
    else:
        q = st.text_input("Search by patient code", key="search")
        shown = [r for r in records if q.lower() in str(r["values"].get("patient_code", "")).lower()]
        table = pd.DataFrame([{
            "Patient code": r["values"].get("patient_code", ""),
            "Age": r["values"].get("age"),
            "Sex": r["values"].get("sex", ""),
            "BP": f"{r['values']['sbp']:g}/{r['values'].get('dbp', 0):g}" if r["values"].get("sbp") else "",
            "BMI": r["values"].get("bmi"),
            "Needs screening": r["values"].get("needs_screening", ""),
            "Encoded": r["encoded_at"][:10],
        } for r in shown])
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button(f"Export all {len(records)} records as CSV", csv_bytes, file_name=csv_name,
                           mime="text/csv", key="export_list")
        labels = {r["id"]: f"{r['values'].get('patient_code', '(no code)')} · encoded {r['encoded_at'][:16]}" for r in shown}
        pick = st.selectbox("Open a record to edit", list(labels), format_func=labels.get, index=None)
        if pick and st.button("Open in form"):
            load_into_form(next(r for r in records if r["id"] == pick))
            st.rerun()

with tab_form:
    ed = st.session_state.editing
    st.subheader(f"Editing {ed['values'].get('patient_code', '')}" if ed else "New record")
    current = read_form()
    current["patient_code"] = ed["values"].get("patient_code") if ed else next_patient_code(records)
    for title, fields in section_fields().items():
        with st.container(border=True):
            st.markdown(f"**{title.split('. ', 1)[1]}**")
            cols = st.columns(3)
            for i, f in enumerate(fields):
                with cols[i % 3]:
                    render_field(f, current)

    if current.get("angina_heart_attack") == "Yes":
        st.warning("Yes to questions 3 to 7: the patient may have angina or heart attack and must see a doctor.")
    if current.get("stroke_tia") == "Yes":
        st.warning("Yes to question 8: the patient may have TIA or stroke and must see a doctor.")

    b1, b2, b3 = st.columns([2, 2, 6])
    if b1.button("Save record", type="primary", width="stretch"):
        if not ed:
            current["patient_code"] = next_patient_code(load_records())
        if len(current) <= 1:
            st.error("Fill in the form before saving.")
        else:
            rec_id = ed["id"] if ed else uuid.uuid4().hex[:12]
            save_record(rec_id, current, ed["encoded_at"] if ed else None)
            clear_form()
            st.toast(f"Saved {current['patient_code']}. Ready for the next form.")
            st.rerun()
    if ed:
        if b2.button("Delete record", width="stretch"):
            st.session_state.confirm_delete = True
        if st.session_state.get("confirm_delete"):
            st.error(f"Delete {ed['values'].get('patient_code', 'this record')} for good?")
            c1, c2, _ = st.columns([1, 1, 8])
            if c1.button("Delete"):
                delete_record(ed["id"])
                st.session_state.confirm_delete = False
                clear_form()
                st.rerun()
            if c2.button("Keep"):
                st.session_state.confirm_delete = False
                st.rerun()
