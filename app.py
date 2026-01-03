import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="Classroom Reflection", layout="wide")
DB_PATH = "teacher_engagement.db"

# -----------------------------
# DATABASE
# -----------------------------
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            teacher_id TEXT,
            school_id TEXT,
            teacher_name TEXT,
            PRIMARY KEY (teacher_id, school_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            class_id TEXT,
            subject_id TEXT,
            school_id TEXT,
            class_size INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id TEXT,
            teacher_id TEXT,
            class_id TEXT,
            subject_id TEXT,
            session_date DATE,
            number_present INTEGER,
            participation_level TEXT,
            attentiveness_level TEXT,
            task_given TEXT,
            note TEXT,
            cei_score REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id TEXT,
            teacher_id TEXT,
            week INTEGER,
            reflection TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# -----------------------------
# SESSION STATE
# -----------------------------
if "teacher_id" not in st.session_state:
    st.session_state.teacher_id = None
if "school_id" not in st.session_state:
    st.session_state.school_id = None

# -----------------------------
# LOGIN
# -----------------------------
def login():
    st.title("Teacher Classroom Reflection")

    school_id = st.text_input("School ID")
    teacher_id = st.text_input("Teacher ID")
    teacher_name = st.text_input("Your Name")

    if st.button("Continue"):
        if school_id and teacher_id and teacher_name:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO teachers VALUES (?, ?, ?)",
                (teacher_id, school_id, teacher_name)
            )
            conn.commit()
            conn.close()

            st.session_state.school_id = school_id
            st.session_state.teacher_id = teacher_id
            st.rerun()
        else:
            st.error("All fields are required")

if not st.session_state.teacher_id:
    login()
    st.stop()

# -----------------------------
# CORE LOGIC
# -----------------------------
# Locked CEI scoring
CEI_WEIGHTS = {
    "participation": 0.4,   # 40% of CEI
    "attentiveness": 0.4,   # 40%
    "presence": 0.2          # 20%
}

CEI_LEVEL_SCORES = {
    "low": 10,
    "medium": 25,
    "high": 40
}

def compute_cei(participation, attentiveness, present, class_size):
    """
    Returns CEI score for a single class session
    """
    if class_size <= 0:
        return 0

    part_score = CEI_LEVEL_SCORES.get(participation, 0)
    att_score  = CEI_LEVEL_SCORES.get(attentiveness, 0)
    presence_score = min((present / class_size) * CEI_LEVEL_SCORES["high"], CEI_LEVEL_SCORES["high"])

    cei = round(
        CEI_WEIGHTS["participation"]*part_score +
        CEI_WEIGHTS["attentiveness"]*att_score +
        CEI_WEIGHTS["presence"]*presence_score,
        2
    )

    return cei

# Locked Engagement Interpretation Rules
ENGAGEMENT_RULES = [
    {"min": 75, "max": 100, "status": "green", "message": "Class is responding well. Keep your current approach."},
    {"min": 60, "max": 75, "status": "yellow", "message": "Engagement is fair. Small adjustments may help."},
    {"min": 0,  "max": 60, "status": "red", "message": "Engagement is low. Consider changing pace or method."}
]

def interpret_engagement(series):
    """
    Input: pandas Series of CEI scores for the filtered class
    Output: status color and message (locked)
    """
    avg = series.mean() if not series.empty else 0
    for rule in ENGAGEMENT_RULES:
        if rule["min"] <= avg < rule["max"]:
            return rule["status"], rule["message"]
    # fallback
    return "red", "Engagement data unclear. Please reflect more consistently."

# -----------------------------
# CLASS SETUP
# -----------------------------
def class_setup():
    st.header("Class Setup")

    with st.form("class_form"):
        class_id = st.text_input("Class name (e.g. JSS2 Blue)")
        subject_id = st.text_input("Subject")
        class_size = st.number_input("Total students", min_value=1)

        submitted = st.form_submit_button("Add Class")

    if submitted:
        conn = get_connection()
        conn.execute(
            "INSERT INTO classes VALUES (?, ?, ?, ?)",
            (class_id, subject_id, st.session_state.school_id, class_size)
        )
        conn.commit()
        conn.close()
        st.success("Class added successfully")

# -----------------------------
# DAILY REFLECTION
# -----------------------------
def daily_reflection():
    st.header("Daily Class Reflection")

    conn = get_connection()
    classes = pd.read_sql(
        "SELECT * FROM classes WHERE school_id=?",
        conn,
        params=(st.session_state.school_id,)
    )
    conn.close()

    if classes.empty:
        st.info("Please add your classes first.")
        return

    classes["label"] = classes["class_id"] + " - " + classes["subject_id"]

    with st.form("daily_form"):
        selection = st.selectbox("Class / Subject", classes["label"].tolist())
        row = classes[classes["label"] == selection].iloc[0]

        session_date = st.date_input("Date", value=date.today())
        present = st.number_input(
            "Number present",
            min_value=0,
            max_value=int(row["class_size"])
        )

        participation = st.selectbox(
            "Participation level",
            ["low", "medium", "high"],
            index=1,
            help="High: ≥30% active, Medium: some interaction, Low: mostly passive"
        )

        attentiveness = st.selectbox(
            "Attentiveness level",
            ["low", "medium", "high"],
            index=1
        )

        task = st.selectbox(
            "Task given",
            ["none", "classwork", "assignment", "test"]
        )

        topic = st.text_area("Topic (today's topic?..)")

        note = st.text_area("Short note (optional)")

        submitted = st.form_submit_button("Save Reflection")

    if submitted:
        cei = compute_cei(
            participation,
            attentiveness,
            present,
            row["class_size"]
        )

        conn = get_connection()
        conn.execute("""
            INSERT INTO daily_reflections (
                school_id, teacher_id, class_id, subject_id,
                session_date, number_present,
                participation_level, attentiveness_level,
                task_given, note, topic, cei_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            st.session_state.school_id,
            st.session_state.teacher_id,
            row["class_id"],
            row["subject_id"],
            session_date,
            present,
            participation,
            attentiveness,
            task,
            topic,
            note,
            cei
        ))
        conn.commit()
        conn.close()

        st.success(f"Reflection saved. Engagement score: {cei}%")

# -----------------------------
# DASHBOARD (FIXED)
# -----------------------------
def teacher_dashboard():
    st.header("Classroom Engagement Trend")

    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM daily_reflections WHERE school_id=? AND teacher_id=?",
        conn,
        params=(st.session_state.school_id, st.session_state.teacher_id)
    )
    conn.close()

    if df.empty:
        st.info("No reflections yet.")
        return

    df["session_date"] = pd.to_datetime(df["session_date"])

    # ---- REQUIRED FILTER STEP ----
    class_filter = st.selectbox("Select class", df["class_id"].unique())
    subject_filter = st.selectbox(
        "Select subject",
        df[df["class_id"] == class_filter]["subject_id"].unique()
    )

    plot_df = df[
        (df["class_id"] == class_filter) &
        (df["subject_id"] == subject_filter)
    ].sort_values("session_date")

    # ---- DEFENSIVE LOGIC ----
    if plot_df.empty or len(plot_df) < 2:
        st.info(
            "Not enough entries yet to show a clear pattern. "
            "Keep reflecting over the next few days."
        )
        st.line_chart(plot_df.set_index("session_date")["cei_score"])
        return

    # ---- VISUAL ----
    st.line_chart(plot_df.set_index("session_date")["cei_score"])

    # ---- INTERPRETATION ----
    status, message = interpret_engagement(plot_df["cei_score"])

    if status == "green":
        st.success(message)
    elif status == "yellow":
        st.warning(message)
    else:
        st.error(message)

# -----------------------------
# NAVIGATION
# -----------------------------
page = st.sidebar.radio(
    "Navigate",
    ["Class Setup", "Daily Reflection", "Dashboard"]
)

if page == "Class Setup":
    class_setup()
elif page == "Daily Reflection":
    daily_reflection()
else:
    teacher_dashboard()
