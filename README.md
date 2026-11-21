# Tell Me What to Check

An interactive behavioral experiment web application built with **Streamlit** to investigate how different AI uncertainty and warning cues affect human trust calibration, verification behavior, and reliance on AI-generated answers.

## Overview
Users answer 24 general-knowledge questions spanning **Indian History & Civics**, **World Geography**, and **Science & Technology**. On each trial, participants submit an initial answer and confidence rating, view an AI suggestion paired with an experimental warning cue, decide whether to verify the claim, and submit their final decision.

## Experimental Design
* **Design:** 2 × 4 within-subjects factorial design
* **AI Accuracy:** Correct vs. Wrong AI suggestion
* **Warning Signal Conditions:**
  * `None` (Control — no warning assigned)
  * `Hedge` (Linguistic uncertainty phrasing)
  * `Badge` (Visual confidence/caution indicator)
  * `Caveat` (Explicit verification prompt)
  * *Shown vs. Hidden counterbalancing across trials*
* **Primary Metrics:** Unassisted accuracy, verification click rate, appropriate reliance, overreliance (accepting wrong AI), under-reliance (rejecting right AI), and post-study survey ratings (including Indian English speaker perception).

## Repository Structure
* `app.py` — Main Streamlit application, trial randomization, UI flow, and automated background telemetry.
* `stimuli.csv` — 24 calibrated trivia items, domains, ground-truth answers, and AI responses.
* `requirements.txt` — Python dependencies for Streamlit Community Cloud deployment.

## Telemetry & Monitoring
Trial-level responses and post-study survey entries are logged asynchronously via HTTP POST to a linked Google Form and aggregated in real time in Google Sheets.
