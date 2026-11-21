import json
import re
import time
import random
import urllib.parse
import urllib.request
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Tell Me What to Check — HCI Study", layout="centered")

GOOGLE_FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSfSRSMFqL8R0ULg5HKLwvCZZ5V8c-bJfJn6rPBimkfFPx9otQ/formResponse"
)

FIELD_MAP = {
    "participant_id": "entry.1017657753",
    "record_type": "entry.890702658",
    "item_id": "entry.990599375",
    "domain": "entry.563673759",
    "signal_arm": "entry.685208798",
    "ai_is_correct": "entry.281299658",
    "user_initial_answer": "entry.331361269",
    "user_initial_correct": "entry.555308524",
    "verified_clicked": "entry.2077279791",
    "final_decision": "entry.205503851",
    "final_correct": "entry.88238036",
    "survey_summary": "entry.2119949638",
}

CELLS = [
    ("Correct", "None"),
    ("Correct", "Hedge"),
    ("Correct", "Badge"),
    ("Correct", "Caveat"),
    ("Wrong", "None"),
    ("Wrong", "Hedge"),
    ("Wrong", "Badge"),
    ("Wrong", "Caveat"),
]

HEDGE_PHRASES = [
    "I'm not sure about this.",
    "I think this is right.",
    "It is likely true.",
    "Probably.",
    "It seems to be the case.",
    "Possibly.",
]


@st.cache_data
def load_stimuli() -> pd.DataFrame:
    return pd.read_csv("stimuli.csv")


def log_row_to_google_sheet(row_data: dict) -> bool:
    """Silently posts a single trial or survey row to the linked Google Form/Sheet."""
    payload = {
        field_id: str(row_data.get(col_name, ""))
        for col_name, field_id in FIELD_MAP.items()
    }
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_FORM_URL,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def generate_participant_schedule(stimuli_df: pd.DataFrame, participant_num: int) -> list:
    """
    24-trial counterbalanced 2x4 within-subjects schedule:
    - 3 trials per cell (12 Correct, 12 Wrong)
    - Signals fire on 2 of 3 Wrong answers and 1 of 3 Correct answers
    """
    trials = []
    for idx, row in stimuli_df.iterrows():
        cell_idx = (idx + participant_num) % 8
        correctness, signal_arm = CELLS[cell_idx]
        slot = (idx // 8) % 3

        if signal_arm == "None":
            flagged = False
        elif correctness == "Wrong":
            flagged = slot in (0, 1)
        else:
            flagged = slot == 0

        ai_text = (
            row["correct_answer"] if correctness == "Correct" else row["wrong_answer"]
        )

        trials.append(
            {
                "item_id": int(row["id"]),
                "domain": row["domain"],
                "question": row["question"],
                "ground_truth": str(row["ground_truth"]),
                "version": correctness,
                "signal_arm": signal_arm,
                "flagged": flagged,
                "ai_text": ai_text,
                "hedge_line": row["hedge_line"],
                "badge_text": row["badge_text"],
                "caveat_line": row["caveat_line"],
            }
        )

    rng = random.Random(participant_num * 101 + 7)
    rng.shuffle(trials)
    return trials


def render_ai_box(trial: dict):
    """Renders the AI answer card and, if flagged, the assigned uncertainty signal."""
    st.markdown("### AI Assistant Response")
    signal_html = ""
    if trial["flagged"]:
        if trial["signal_arm"] == "Hedge":
            signal_html = (
                f"<p style='color:#9a3412; margin-top:10px; margin-bottom:0; font-style:italic;'>"
                f"{trial['hedge_line']}</p>"
            )
        elif trial["signal_arm"] == "Badge":
            signal_html = (
                f"<div style='display:inline-block; background-color:#ffedd5; color:#c2410c; "
                f"border:1px solid #fb923c; border-radius:999px; padding:3px 12px; "
                f"font-size:0.85rem; font-weight:600; margin-top:10px;'>"
                f"⚠ {trial['badge_text']}</div>"
            )
        elif trial["signal_arm"] == "Caveat":
            signal_html = (
                f"<p style='color:#9a3412; margin-top:10px; margin-bottom:0; font-weight:600;'>"
                f"{trial['caveat_line']}</p>"
            )

    box_html = f"""
    <div style="background-color:#f8fafc; border:1px solid #cbd5e1; border-radius:10px; padding:16px; margin-bottom:16px;">
        <div style="font-size:1.08rem; color:#0f172a;">{trial['ai_text']}</div>
        {signal_html}
    </div>
    """
    st.markdown(box_html, unsafe_allow_html=True)


def check_initial_correct(guess: str, ground_truth: str) -> int:
    """Normalizes minor formatting differences (e.g. '35' vs '35 years', '100' vs '100°C')."""
    def clean(text: str) -> str:
        t = text.lower().strip()
        t = t.replace("°c", "").replace("°", "")
        t = re.sub(r"[^\w\s]", "", t)
        t = re.sub(r"\b(years|year|spokes|lord|mount|mt|the)\b", "", t)
        return " ".join(t.split())

    g = clean(guess)
    gt = clean(ground_truth)
    if not g or g in ("dont know", "idk", "na", "none", "unsure"):
        return 0
    if g == gt:
        return 1
    if len(gt) >= 3 and gt in g:
        return 1
    return 0


def score_appropriate_reliance(version: str, decision: str) -> int:
    """1 = Appropriate reliance (Accept if Correct; Verify/Reject if Wrong), 0 = Otherwise."""
    if version == "Correct":
        return 1 if decision == "Accept" else 0
    return 1 if decision in ("Verify", "Reject") else 0


def format_signal_label(trial: dict) -> str:
    if trial["signal_arm"] == "None":
        return "None"
    return f"{trial['signal_arm']} (Shown)" if trial["flagged"] else f"{trial['signal_arm']} (Hidden)"


# Initialize session state
if "stage" not in st.session_state:
    st.session_state.stage = "welcome"
    st.session_state.trial_idx = 0
    st.session_state.stage_start = time.time()


# --- STAGE 0: WELCOME & CONSENT ---
if st.session_state.stage == "welcome":
    st.title("AI Fact-Checking & Reliance Study")
    st.write(
        "In this study, you will answer 24 short factual questions from memory and then "
        "evaluate responses generated by an AI assistant."
    )
    st.info(
        "**Instructions:** Please answer strictly from memory—do not search online "
        "or use external references. The session takes about 10–15 minutes."
    )

    consent = st.checkbox(
        "I consent to participate and have my anonymous responses recorded."
    )

    if st.button("Start Quiz", disabled=not consent, type="primary"):
        p_num = random.randint(1000, 9999)
        stimuli_df = load_stimuli()

        st.session_state.participant_id = f"P-{p_num}"
        st.session_state.participant_num = p_num
        st.session_state.trials = generate_participant_schedule(stimuli_df, p_num)
        st.session_state.trial_idx = 0
        st.session_state.stage = "recall"
        st.session_state.stage_start = time.time()
        st.rerun()


# --- STAGE 1: BASELINE RECALL & CONFIDENCE ---
elif st.session_state.stage == "recall":
    idx = st.session_state.trial_idx
    total = len(st.session_state.trials)
    trial = st.session_state.trials[idx]

    st.progress(idx / total, text=f"Question {idx + 1} of {total}")
    st.subheader(trial["question"])

    user_guess = st.text_input(
        "Your answer from memory (type 'don't know' if unsure):",
        key=f"guess_{idx}",
    )
    user_conf = st.slider(
        "How confident are you in your answer? (1 = Not at all, 7 = Completely sure)",
        min_value=1,
        max_value=7,
        value=4,
        key=f"conf_{idx}",
    )

    if st.button("Submit My Answer & See AI Response", disabled=not user_guess.strip()):
        st.session_state.current_recall = {
            "user_initial_answer": user_guess.strip(),
            "initial_confidence": user_conf,
            "time_recall_sec": round(time.time() - st.session_state.stage_start, 2),
        }
        st.session_state.stage = "decision"
        st.session_state.stage_start = time.time()
        st.rerun()


# --- STAGE 2: AI EXPOSURE & ACCEPT / VERIFY / REJECT ---
elif st.session_state.stage == "decision":
    idx = st.session_state.trial_idx
    total = len(st.session_state.trials)
    trial = st.session_state.trials[idx]

    st.progress((idx + 0.5) / total, text=f"Question {idx + 1} of {total}")
    st.markdown(f"**Question:** {trial['question']}")
    st.caption(
        f"Your guess: *{st.session_state.current_recall['user_initial_answer']}* "
        f"(Confidence: {st.session_state.current_recall['initial_confidence']}/7)"
    )

    render_ai_box(trial)
    st.write("How would you like to respond to the AI's answer?")

    col1, col2, col3 = st.columns(3)
    chosen = None
    if col1.button("Accept", use_container_width=True):
        chosen = "Accept"
    if col2.button("Verify", use_container_width=True):
        chosen = "Verify"
    if col3.button("Reject", use_container_width=True):
        chosen = "Reject"

    if chosen in ("Accept", "Reject"):
        decision_time = round(time.time() - st.session_state.stage_start, 2)
        ans = st.session_state.current_recall["user_initial_answer"]
        conf = st.session_state.current_recall["initial_confidence"]
        t_rec = st.session_state.current_recall["time_recall_sec"]

        log_row_to_google_sheet(
            {
                "participant_id": st.session_state.participant_id,
                "record_type": "trial",
                "item_id": trial["item_id"],
                "domain": trial["domain"],
                "signal_arm": format_signal_label(trial),
                "ai_is_correct": trial["version"],
                "user_initial_answer": f"{ans} (conf:{conf}/7)",
                "user_initial_correct": check_initial_correct(ans, trial["ground_truth"]),
                "verified_clicked": 0,
                "final_decision": chosen,
                "final_correct": score_appropriate_reliance(trial["version"], chosen),
                "survey_summary": f"trial={idx + 1}; init={chosen}; t_rec={t_rec}s; t_dec={decision_time}s",
            }
        )

        if idx + 1 < total:
            st.session_state.trial_idx += 1
            st.session_state.stage = "recall"
            st.session_state.stage_start = time.time()
        else:
            st.session_state.stage = "survey"
        st.rerun()

    elif chosen == "Verify":
        st.session_state.decision_time_pre_verify = round(
            time.time() - st.session_state.stage_start, 2
        )
        st.session_state.stage = "verify_snippet"
        st.session_state.stage_start = time.time()
        st.rerun()


# --- STAGE 2B: VERIFICATION SNIPPET & POST-CHECK DECISION ---
elif st.session_state.stage == "verify_snippet":
    idx = st.session_state.trial_idx
    total = len(st.session_state.trials)
    trial = st.session_state.trials[idx]

    st.progress((idx + 0.8) / total, text=f"Question {idx + 1} of {total} — Verification")
    st.markdown(f"**Question:** {trial['question']}")
    render_ai_box(trial)

    st.success(
        f"**Verified Reference Snippet:** The ground-truth answer is **{trial['ground_truth']}**."
    )
    st.write(
        "Now that you have checked the reference snippet, what is your final decision on the AI answer?"
    )

    c1, c2 = st.columns(2)
    final_choice = None
    if c1.button("Final: Accept AI Answer", use_container_width=True):
        final_choice = "Accept"
    if c2.button("Final: Reject AI Answer", use_container_width=True):
        final_choice = "Reject"

    if final_choice:
        verify_time = round(time.time() - st.session_state.stage_start, 2)
        ans = st.session_state.current_recall["user_initial_answer"]
        conf = st.session_state.current_recall["initial_confidence"]
        t_rec = st.session_state.current_recall["time_recall_sec"]
        t_dec = st.session_state.decision_time_pre_verify

        log_row_to_google_sheet(
            {
                "participant_id": st.session_state.participant_id,
                "record_type": "trial",
                "item_id": trial["item_id"],
                "domain": trial["domain"],
                "signal_arm": format_signal_label(trial),
                "ai_is_correct": trial["version"],
                "user_initial_answer": f"{ans} (conf:{conf}/7)",
                "user_initial_correct": check_initial_correct(ans, trial["ground_truth"]),
                "verified_clicked": 1,
                "final_decision": final_choice,
                "final_correct": score_appropriate_reliance(trial["version"], "Verify"),
                "survey_summary": (
                    f"trial={idx + 1}; init=Verify; t_rec={t_rec}s; "
                    f"t_dec={t_dec}s; t_ver={verify_time}s"
                ),
            }
        )

        if idx + 1 < total:
            st.session_state.trial_idx += 1
            st.session_state.stage = "recall"
            st.session_state.stage_start = time.time()
        else:
            st.session_state.stage = "survey"
        st.rerun()


# --- STAGE 3: POST-TASK SURVEY & OPTIONAL RQ3 ---
elif st.session_state.stage == "survey":
    st.title("Post-Task Questionnaire")

    st.subheader(
        "1. Experience with the AI Warnings (1 = Strongly Disagree, 7 = Strongly Agree)"
    )
    useful_hedge = st.slider("Generic hedges ('I'm not sure') were useful:", 1, 7, 4)
    annoy_hedge = st.slider("Generic hedges ('I'm not sure') were annoying:", 1, 7, 4)

    useful_badge = st.slider("Orange 'Low confidence' badges were useful:", 1, 7, 4)
    annoy_badge = st.slider("Orange 'Low confidence' badges were annoying:", 1, 7, 4)

    useful_caveat = st.slider(
        "Specific caveats ('Check X; I'm least sure...') were useful:", 1, 7, 4
    )
    annoy_caveat = st.slider(
        "Specific caveats ('Check X; I'm least sure...') were annoying:", 1, 7, 4
    )

    trust_overall = st.slider(
        "Overall, I could rely on the AI assistant appropriately:", 1, 7, 4
    )

    st.subheader("2. Background Questions")
    native_lang = st.text_input("Native / first language:", value="Hindi")
    english_comfort = st.slider(
        "Comfort reading and working in English (1 = Low, 7 = Native/Fluent):", 1, 7, 6
    )
    ai_freq = st.selectbox(
        "How often do you use AI tools (like ChatGPT, Gemini, Claude)?",
        ["Daily", "Several times a week", "Weekly", "Monthly or less", "Never"],
    )

    st.subheader("3. Optional: Interpreting Uncertainty Phrases (RQ3)")
    st.caption(
        "If an AI uses each phrase below, what percentage chance (0–100%) do you think the answer is correct?"
    )
    rq3_ratings = {}
    for phrase in HEDGE_PHRASES:
        rq3_ratings[phrase] = st.slider(
            f'"{phrase}"', 0, 100, 50, key=f"rq3_{phrase}"
        )

    if st.button("Submit Final Responses", disabled=not native_lang.strip(), type="primary"):
        survey_payload = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "useful_hedge": useful_hedge,
            "annoy_hedge": annoy_hedge,
            "useful_badge": useful_badge,
            "annoy_badge": annoy_badge,
            "useful_caveat": useful_caveat,
            "annoy_caveat": annoy_caveat,
            "trust_overall": trust_overall,
            "native_language": native_lang.strip(),
            "english_comfort": english_comfort,
            "ai_use_frequency": ai_freq,
            "rq3": rq3_ratings,
        }

        log_row_to_google_sheet(
            {
                "participant_id": st.session_state.participant_id,
                "record_type": "survey",
                "survey_summary": json.dumps(survey_payload),
            }
        )

        st.session_state.stage = "done"
        st.rerun()


# --- STAGE 4: COMPLETION ---
elif st.session_state.stage == "done":
    st.title("Study Complete")
    st.success(
        "Thank you for participating! Your responses have been recorded automatically. "
        "You may now close this browser tab."
    )
