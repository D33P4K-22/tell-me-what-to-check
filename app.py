import os
import time
import random
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Tell Me What to Check — HCI Study", layout="centered")

DATA_DIR = "study_logs"
os.makedirs(DATA_DIR, exist_ok=True)

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


def load_stimuli() -> pd.DataFrame:
    return pd.read_csv("stimuli.csv")


def generate_quick_demo_schedule(stimuli_df: pd.DataFrame) -> list:
    """4-trial demo showcasing one example of each warning style."""
    demo_specs = [
        (0, "Correct", "None", False),
        (1, "Wrong", "Hedge", True),
        (2, "Wrong", "Badge", True),
        (3, "Wrong", "Caveat", True),
    ]
    trials = []
    for row_idx, correctness, signal_arm, flagged in demo_specs:
        row = stimuli_df.iloc[row_idx]
        ai_text = (
            row["correct_answer"] if correctness == "Correct" else row["wrong_answer"]
        )
        trials.append(
            {
                "item_id": int(row["id"]),
                "domain": row["domain"],
                "question": row["question"],
                "ground_truth": row["ground_truth"],
                "version": correctness,
                "signal_arm": signal_arm,
                "flagged": flagged,
                "ai_text": ai_text,
                "hedge_line": row["hedge_line"],
                "badge_text": row["badge_text"],
                "caveat_line": row["caveat_line"],
            }
        )
    return trials


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
        slot = (idx // 8) % 3  # 0, 1, or 2 across the 3 items per cell

        if signal_arm == "None":
            flagged = False
        elif correctness == "Wrong":
            flagged = slot in (0, 1)  # Fires on 2 of 3 wrong answers
        else:
            flagged = slot == 0  # Fires on 1 of 3 correct answers

        ai_text = (
            row["correct_answer"] if correctness == "Correct" else row["wrong_answer"]
        )

        trials.append(
            {
                "item_id": int(row["id"]),
                "domain": row["domain"],
                "question": row["question"],
                "ground_truth": row["ground_truth"],
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


def score_appropriate_reliance(version: str, decision: str) -> int:
    """1 = Appropriate reliance (Accept if Correct; Verify/Reject if Wrong), 0 = Otherwise."""
    if version == "Correct":
        return 1 if decision == "Accept" else 0
    return 1 if decision in ("Verify", "Reject") else 0


# Initialize session state
if "stage" not in st.session_state:
    st.session_state.stage = "welcome"
    st.session_state.trial_idx = 0
    st.session_state.logs = []
    st.session_state.stage_start = time.time()


# --- STAGE 0: WELCOME & CONSENT ---
if st.session_state.stage == "welcome":
    st.title("AI Fact-Checking & Reliance Study")
    st.write(
        "In this study, you will answer short factual questions from memory and then "
        "evaluate responses generated by an AI assistant."
    )
    st.info(
        "**Instructions:** Please answer strictly from memory—do not search online "
        "or use external references. The full session takes about 15–20 minutes."
    )

    p_id = st.text_input("Participant ID (e.g., P01, DEMO01):", value="DEMO01").strip()
    run_mode = st.radio(
        "Session Mode:",
        [
            "Quick Demo (4 Trials — 1 per signal type)",
            "Full Study (24 Trials — Counterbalanced 2x4 Design)",
        ],
    )
    consent = st.checkbox(
        "I consent to participate and have my anonymous responses recorded."
    )

    if st.button("Start Study", disabled=not (p_id and consent)):
        digits = "".join(ch for ch in p_id if ch.isdigit())
        p_num = int(digits) if digits else abs(hash(p_id)) % 100
        stimuli_df = load_stimuli()

        st.session_state.participant_id = p_id
        st.session_state.participant_num = p_num
        st.session_state.run_mode = run_mode
        if run_mode.startswith("Quick Demo"):
            st.session_state.trials = generate_quick_demo_schedule(stimuli_df)
        else:
            st.session_state.trials = generate_participant_schedule(stimuli_df, p_num)

        st.session_state.trial_idx = 0
        st.session_state.logs = []
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
        st.session_state.logs.append(
            {
                "participant_id": st.session_state.participant_id,
                "trial_num": idx + 1,
                "item_id": trial["item_id"],
                "domain": trial["domain"],
                "version": trial["version"],
                "signal_arm": trial["signal_arm"],
                "flagged": int(trial["flagged"]),
                "user_initial_answer": st.session_state.current_recall["user_initial_answer"],
                "initial_confidence": st.session_state.current_recall["initial_confidence"],
                "initial_decision": chosen,
                "verify_snippet_opened": 0,
                "final_decision": chosen,
                "decision_changed": 0,
                "decision_correct": score_appropriate_reliance(trial["version"], chosen),
                "time_recall_sec": st.session_state.current_recall["time_recall_sec"],
                "time_decision_sec": decision_time,
                "time_verify_sec": 0.0,
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
        st.session_state.logs.append(
            {
                "participant_id": st.session_state.participant_id,
                "trial_num": idx + 1,
                "item_id": trial["item_id"],
                "domain": trial["domain"],
                "version": trial["version"],
                "signal_arm": trial["signal_arm"],
                "flagged": int(trial["flagged"]),
                "user_initial_answer": st.session_state.current_recall["user_initial_answer"],
                "initial_confidence": st.session_state.current_recall["initial_confidence"],
                "initial_decision": "Verify",
                "verify_snippet_opened": 1,
                "final_decision": final_choice,
                "decision_changed": 1,
                "decision_correct": score_appropriate_reliance(trial["version"], "Verify"),
                "time_recall_sec": st.session_state.current_recall["time_recall_sec"],
                "time_decision_sec": st.session_state.decision_time_pre_verify,
                "time_verify_sec": verify_time,
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

    if st.button("Finish & Save Responses", disabled=not native_lang.strip()):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pid = st.session_state.participant_id

        trials_out = pd.DataFrame(st.session_state.logs)
        trials_path = f"{DATA_DIR}/{pid}_{ts}_trials.csv"
        trials_out.to_csv(trials_path, index=False)

        survey_row = {
            "participant_id": pid,
            "mode": st.session_state.run_mode,
            "timestamp": ts,
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
        }
        for phrase, val in rq3_ratings.items():
            survey_row[f"rq3_{phrase}"] = val

        survey_out = pd.DataFrame([survey_row])
        survey_path = f"{DATA_DIR}/{pid}_{ts}_survey.csv"
        survey_out.to_csv(survey_path, index=False)

        st.session_state.saved_trials_csv = trials_out.to_csv(index=False)
        st.session_state.saved_survey_csv = survey_out.to_csv(index=False)
        st.session_state.saved_prefix = f"{pid}_{ts}"
        st.session_state.stage = "done"
        st.rerun()


# --- STAGE 4: COMPLETION & DATA PREVIEW ---
elif st.session_state.stage == "done":
    st.success("Thank you! Your responses have been saved to the `study_logs/` folder.")
    st.write("You can also download or inspect the logged data directly below:")

    col_a, col_b = st.columns(2)
    col_a.download_button(
        label="Download Trials CSV",
        data=st.session_state.saved_trials_csv,
        file_name=f"{st.session_state.saved_prefix}_trials.csv",
        mime="text/csv",
        use_container_width=True,
    )
    col_b.download_button(
        label="Download Survey CSV",
        data=st.session_state.saved_survey_csv,
        file_name=f"{st.session_state.saved_prefix}_survey.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.subheader("Logged Trial Data Preview")
    st.dataframe(pd.DataFrame(st.session_state.logs))

    if st.button("Restart / Run Another Session"):
        st.session_state.stage = "welcome"
        st.session_state.trial_idx = 0
        st.session_state.logs = []
        st.rerun()
