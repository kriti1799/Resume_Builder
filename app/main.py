# app/main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from app.agent import resume_agent_app # Import your compiled LangGraph workflow
from app.utils import extract_text_from_file
import json

app = FastAPI(title="Resume Parsing Agent API")

# --- ENDPOINT 1: Initial Upload & Parse ---
@app.post("/process-documents/")
async def process_documents(
    email: str = Form(...),
    resume: UploadFile = File(...)
):
    
    resume_bytes = await resume.read()
    resume_text = extract_text_from_file(resume_bytes, resume.filename)

    if not resume_text or "Error" in resume_text or "Unsupported" in resume_text:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {resume_text}")
    
    thread_config = {"configurable": {"thread_id": email}}
    initial_state = {
        "resume_text": resume_text,
        "chat_history": [],
        "extracted_data": None,
        "pending_questions": []
    }

    
    # We use the user's email as the thread_id to track their specific session
    thread_config = {"configurable": {"thread_id": email}}
    initial_state = {
        "resume_text": resume_text,
        "chat_history": [],
        "extracted_data": None,
        "pending_questions": []
    }
    
    # Run the graph until it hits the breakpoint
    for event in resume_agent_app.stream(initial_state, config=thread_config):
        pass
        
    state = resume_agent_app.get_state(thread_config)
    
    # Check if the graph paused at the 'human_input' node
    if state.next == ('human_input',):
        return {
            "status": "waiting_for_user",
            "message": "The agent needs more information.",
            "questions": state.values.get("pending_questions", []),
            "thread_id": email 
        }

    extracted_json = state.values.get("extracted_data") # Or state.values.get for the first endpoint

    # --- NEW: Save the JSON to a file for your teammates ---
    with open("master_candidate_profile.json", "w") as f:
        json.dump(extracted_json, f, indent=4)
    # If no questions, it finished completely on the first try!
    return {
        "status": "completed",
        "parsed_data": state.values.get("extracted_data")
    }

# --- Pydantic Schema for the second endpoint ---
class UserAnswerPayload(BaseModel):
    thread_id: str
    answers: str # e.g., "I actually improved the EBITDA by 40%."

# --- ENDPOINT 2: Resume with Human Input ---
@app.post("/answer-questions/")
async def answer_questions(payload: UserAnswerPayload):
    thread_config = {"configurable": {"thread_id": payload.thread_id}}
    state = resume_agent_app.get_state(thread_config)
    
    # Guardrail: Ensure the graph is actually paused and waiting
    if state.next != ('human_input',):
        raise HTTPException(status_code=400, detail="This session is not waiting for input.")
    
    user_input_clean = payload.answers.strip().lower()
    if user_input_clean in ["stop", "quit", "exit", "skip", "enough"]:
        return {
            "status": "completed",
            "message": "Interview stopped by user.",
            "parsed_data": state.values.get("extracted_data")
        }
        
    questions_asked = state.values.get("pending_questions", [])
    
    # Append the Q&A to the LangGraph chat history state
    new_chat_history = state.values["chat_history"] + [
        {"role": "assistant", "content": str(questions_asked)},
        {"role": "user", "content": payload.answers}
    ]
    
    # Update the state with the user's answers
    resume_agent_app.update_state(thread_config, {"chat_history": new_chat_history})
    
    # Resume the graph (passing None tells it to continue from the breakpoint)
    for event in resume_agent_app.stream(None, config=thread_config):
        pass
        
    # Check the state again
    final_state = resume_agent_app.get_state(thread_config)
    
    # Did the agent ask MORE questions based on the new info?
    if final_state.next == ('human_input',):
        return {
            "status": "waiting_for_user",
            "message": "Follow-up questions from the agent.",
            "questions": final_state.values.get("pending_questions", []),
            "thread_id": payload.thread_id
        }
    
    extracted_json = final_state.values.get("extracted_data") # Or state.values.get for the first endpoint
    
    # --- NEW: Save the JSON to a file for your teammates ---
    with open("master_candidate_profile.json", "w") as f:
        json.dump(extracted_json, f, indent=4)
        
    # If done, return the master JSON!
    return {
        "status": "completed",
        "parsed_data": final_state.values.get("extracted_data")
    }