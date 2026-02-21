import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.title("Resume Builder AI Agent 🤖")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "status" not in st.session_state:
    st.session_state.status = "upload" # upload, chatting, or completed

# --- PAGE 1: File Upload ---
if st.session_state.status == "upload":
    email = st.text_input("Enter your email (Thread ID):")
    uploaded_file = st.file_uploader("Upload your Resume (PDF/DOCX)", type=["pdf", "docx"])
    
    if st.button("Start Interview") and email and uploaded_file:
        with st.spinner("Agent is reading your resume..."):
            files = {"resume": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {"email": email}
            
            # Hit your FastAPI endpoint
            response = requests.post(f"{API_URL}/process-documents/", data=data, files=files).json()
            
            st.session_state.thread_id = response.get("thread_id", email)
            
            if response["status"] == "waiting_for_user":
                # Save the agent's first question to chat history
                first_question = response["questions"][0]
                st.session_state.messages.append({"role": "assistant", "content": first_question})
                st.session_state.status = "chatting"
                st.rerun()
            elif response["status"] == "completed":
                st.success("Your resume was perfect! No questions needed.")
                st.json(response["parsed_data"])

# --- PAGE 2: The Chatbot Interface ---
elif st.session_state.status == "chatting":
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
            response = requests.post(f"{API_URL}/answer-questions/", json=payload).json()
            
            if response["status"] == "waiting_for_user":
                next_question = response["questions"][0]
                st.session_state.messages.append({"role": "assistant", "content": next_question})
                st.rerun()
            elif response["status"] == "completed":
                st.session_state.status = "completed"
                st.session_state.final_json = response["parsed_data"]
                st.rerun()

# --- PAGE 3: The Result ---
elif st.session_state.status == "completed":
    st.success("Interview Complete! Here is your structured master profile.")
    st.json(st.session_state.final_json)
    if st.button("Start Over"):
        st.session_state.clear()
        st.rerun()