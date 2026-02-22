import streamlit as st
import requests
from pathlib import Path

API_URL = "http://localhost:8000"
APP_DIR = Path(__file__).resolve().parent

st.title("Resume Builder AI Agent 🤖")

# Initialize chat history in session state
if "status" not in st.session_state:
    st.session_state.status = "login"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "target_job_url" not in st.session_state:
    st.session_state.target_job_url = ""
if "upskill_agent" not in st.session_state:
    st.session_state.upskill_agent = None


def safe_post_json(url, **kwargs):
    try:
        res = requests.post(url, timeout=120, **kwargs)
    except requests.RequestException as exc:
        st.error(f"Request failed: {exc}")
        return None

    if res.status_code != 200:
        st.error(f"⚠️ Backend Error {res.status_code}")
        st.error(f"Raw backend response: {res.text}")
        return None

    try:
        return res.json()
    except ValueError:
        st.error("Backend returned a non-JSON response.")
        st.error(f"Raw backend response: {res.text}")
        return None

# ----- PAGE 0: Login ---

if st.session_state.status == "login":
    st.subheader("Welcome! Please log in.")
    name = st.text_input("Full Name")
    email = st.text_input("Email Address")

    if st.button("Continue") and name and email:
        with st.spinner("Checking profile..."):
            response = safe_post_json(f"{API_URL}/auth/", json={"name": name, "email": email})
            
            st.session_state.thread_id = email
            if not response:
                st.stop()

            st.session_state.thread_id = email
            if response["status"] == "existing_user":
                if response.get("has_saved_master"):
                    st.session_state.final_json = response["parsed_data"]
                    st.session_state.status = "dashboard"
                else:
                    st.info("No completed master resume found yet. Please upload your resume to start the interview.")
                    st.session_state.status = "upload"
                st.rerun()
            else:
                st.success(response["message"])
                st.session_state.status = "upload" 
                st.rerun()

# --- PAGE 1: File Upload ---
elif st.session_state.status == "upload":
    st.subheader("Let's build your profile.")
    uploaded_file = st.file_uploader("Upload your Resume (PDF/DOCX)", type=["pdf", "docx"])
    
    if st.button("Start Interview") and uploaded_file:
        with st.spinner("Agent is reading your resume..."):
            files = {"resume": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {"email": st.session_state.thread_id} 
            
            response = safe_post_json(f"{API_URL}/process-documents/", data=data, files=files)
            if not response:
                st.stop()

            if response["status"] == "waiting_for_user":
                first_question = response["questions"][0]
                # Safely get the remaining count
                st.session_state.remaining_questions = response.get("remaining_questions", "?")
                st.session_state.final_json = response.get("parsed_data", {})
                st.session_state.focus_field = response.get("focus_field", "Profile Overview")
                st.session_state.messages.append({"role": "assistant", "content": first_question})
                st.session_state.status = "chatting"
                st.rerun()
            elif response["status"] == "completed":
                st.success("Your resume was perfect! No questions needed.")
                st.session_state.final_json = response["parsed_data"]
                st.session_state.status = "completed"
                st.rerun()

# --- PAGE 2: The Chatbot Interface ---
elif st.session_state.status == "chatting":

    with st.sidebar:
        current_focus = st.session_state.get("focus_field", "Profile Overview")
        
        st.subheader(f"Updating: {current_focus.replace('_', ' ').title()} ⚙️")
        st.caption("Watch the AI update this specific section in real-time!")
        
        # Pull ONLY that specific key from the master JSON to display
        master_json = st.session_state.get("final_json", {})

        if current_focus in master_json:
            st.json({current_focus: master_json[current_focus]})
        else:
            # Fallback if the field isn't explicitly found
            st.json(master_json)

    col1, col2 = st.columns([3, 1])

    with col1:
        # Assuming you passed remaining_questions from the backend into the session state
        count = st.session_state.get("remaining_questions", "?")
        st.caption(f"📝 Approximately {count} questions remaining to perfect your profile.")
    
    with col2:
        if st.button("🛑 Stop & Save", use_container_width=True):
            with st.spinner("Saving profile..."):
                # Sending "stop" triggers our backend intercept to save and exit!
                payload = {"thread_id": st.session_state.thread_id, "answers": "stop"}
                response = safe_post_json(f"{API_URL}/answer-questions/", json=payload)
                if not response:
                    st.stop()
                st.session_state.status = "completed"
                st.session_state.final_json = response["parsed_data"]
                st.rerun()
    st.divider()
    # Display previous messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # User input field
    if prompt := st.chat_input("Type your answer here..."):
        # Display user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Send answer to backend
        with st.spinner("Agent is thinking..."):
            payload = {"thread_id": st.session_state.thread_id, "answers": prompt}
            response = safe_post_json(f"{API_URL}/answer-questions/", json=payload)
            if not response:
                st.stop()
            
            if response["status"] == "waiting_for_user":
                next_question = response["questions"][0]
                # Update the remaining count in session state from the backend response
                st.session_state.remaining_questions = response.get("remaining_questions", "?")
                st.session_state.focus_field = response.get("focus_field", st.session_state.get("focus_field", "Profile Overview"))
                st.session_state.messages.append({"role": "assistant", "content": next_question})
                st.rerun()
            elif response["status"] == "completed":
                st.session_state.status = "completed"
                st.session_state.final_json = response.get("parsed_data", {})
                st.rerun()

# --- PAGE 3: The Result ---
elif st.session_state.status == "dashboard" or st.session_state.status == "completed":
    st.success("Your Master Candidate Profile is ready!")
    st.json(st.session_state.final_json)
 
    # --- UPDATE THIS BUTTON TO TRANSITION ---
    if st.button("Tailor Resume for a Job (Workstream 2)"):
        st.session_state.status = "tailoring"
        st.rerun()
    if st.button("Build Upskill Plan (Workstream 3)"):
        if not st.session_state.get("target_job_url"):
            st.warning("Please complete Workstream 2 first so we can use the job URL for upskilling.")
        else:
            st.session_state.status = "upskilling"
            st.session_state.upskill_agent = None
            st.rerun()
    # ----------------------------------------
        
    if st.button("Log Out"):
        st.session_state.clear()
        st.rerun()


# --- PAGE 5: Tailoring Engine (Workstream 2) ---
elif st.session_state.status == "tailoring":
    st.subheader("Workstream 2: ATS Tailoring Engine 🎯")
    st.markdown("Paste a Job Description URL below. Our agent will analyze the role and rewrite your master profile to perfectly match the ATS requirements.")
    
    job_url = st.text_input("Job Description URL:")
    if job_url:
        st.session_state.target_job_url = job_url
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Generate Tailored PDF", type="primary", use_container_width=True):
            if job_url:
                with st.spinner("Tailoring your resume... This involves 2 AI passes and compiling LaTeX, so it may take a minute!"):
                    import json
                    
                    # 1. Set up the exact folder structure your friend's script expects
                    SCRIPT_DIR = APP_DIR
                    JSON_DIR = SCRIPT_DIR / "json"
                    JSON_DIR.mkdir(exist_ok=True)
                    
                    # 2. Write the JSON and URL to disk so the script can find them
                    with open(JSON_DIR / "info.json", "w") as f:
                        json.dump(st.session_state.final_json, f)
                        
                    
                        
                    # 3. Import and execute your friend's script
                    try:
                        import resume_builder
                        
                        # Run the pipeline! It returns the path to the finished PDF.
                        pdf_file_path = resume_builder.run(job_url=job_url, info_path=JSON_DIR / "info.json")
                        
                        is_pdf = pdf_file_path.suffix.lower() == ".pdf"
                        if is_pdf:
                            st.success("Resume successfully tailored and compiled!")
                        else:
                            st.warning("LaTeX generated successfully, but pdflatex is not installed. Download the .tex file.")

                        # 4. Provide the Download Button
                        with open(pdf_file_path, "rb") as pdf_data:
                            st.download_button(
                                label="⬇️ Download Tailored PDF" if is_pdf else "⬇️ Download Tailored .tex",
                                data=pdf_data,
                                file_name=pdf_file_path.name,
                                mime="application/pdf" if is_pdf else "text/plain"
                            )
                        if st.button("Next: Build Upskill Plan", use_container_width=True):
                            st.session_state.target_job_url = job_url
                            st.session_state.status = "upskilling"
                            st.session_state.upskill_agent = None
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to generate resume: {str(e)}")
            else:
                st.warning("Please paste a Job Description URL first.")
                
    with col2:
        if st.button("Back to Dashboard", use_container_width=True):
            st.session_state.status = "dashboard"
            st.rerun()

# --- PAGE 6: Upskill Agent (Workstream 3) ---
elif st.session_state.status == "upskilling":
    st.subheader("Workstream 3: Upskill Planning Agent 🚀")
    st.caption("This uses your saved master profile + target job URL from tailoring.")

    if not st.session_state.get("final_json"):
        st.error("No master profile found. Please complete the interview flow first.")
        st.stop()
    if not st.session_state.get("target_job_url"):
        st.error("No target job URL found. Please complete Workstream 2 first.")
        st.stop()

    if st.session_state.upskill_agent is None:
        try:
            import os
            import resume_builder
            from upskill_llm import LLMClient
            from upskill_agent import UpskillAgent

            jd_url = st.session_state.target_job_url
            jd_text = resume_builder.fetch_job_description(jd_url) if jd_url.startswith("http") else jd_url
            provider = os.environ.get("UPSKILL_LLM_PROVIDER", "openai")
            llm = LLMClient(provider=provider)
            agent = UpskillAgent(llm)
            agent.start(st.session_state.final_json, jd_text)
            st.session_state.upskill_agent = agent
        except Exception as e:
            st.error(f"Failed to initialize upskill agent: {e}")
            st.stop()

    agent = st.session_state.upskill_agent
    context = agent.context
    current_stage = context.get("current_stage", "")

    for msg in context.get("conversation", []):
        role = "assistant" if msg["speaker"] == "agent" else "user"
        with st.chat_message(role):
            st.markdown(msg["text"])

    if plan := context.get("plan"):
        st.markdown("### Current Plan")
        st.markdown(plan)

    if user_msg := st.chat_input("Respond to continue building/refining your plan..."):
        if current_stage == "target_job_confirmation":
            agent.handle_user_response(user_msg)
        elif current_stage == "follow_ups":
            agent.handle_followup_response(user_msg)
        else:
            agent.refine_plan(user_msg)
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save Plan", use_container_width=True):
            try:
                from pathlib import Path
                import re

                name = (
                    (st.session_state.final_json.get("personal_info") or {}).get("name")
                    or "candidate"
                )
                safe = re.sub(r"[^\w\s-]", "", str(name)).replace(" ", "_")
                out_path = Path.cwd() / f"upskill_plan_{safe}.md"
                out_path.write_text(context.get("plan", ""), encoding="utf-8")
                st.success(f"Saved to {out_path.name}")
            except Exception as e:
                st.error(f"Could not save plan: {e}")
    with col2:
        if st.button("Back to Dashboard", use_container_width=True):
            st.session_state.status = "dashboard"
            st.rerun()
