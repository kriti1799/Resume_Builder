from typing import TypedDict, List, Optional, Dict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app import schemas

# 1. Define the State
class AgentState(TypedDict):
    resume_text: str
    chat_history: List[Dict[str, str]]
    extracted_data: Optional[dict]
    pending_questions: List[str]
    remaining_questions: int
    current_focus_field: str
    is_complete: bool

# 2. Define the AI Node
def process_resume_node(state: AgentState):
    # Initialize the LLM (Requires OPENAI_API_KEY in your docker-compose environment)
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Force the LLM to output the exact Pydantic schema we defined
    structured_llm = llm.with_structured_output(schemas.ExtractionResult)

    formatted_history = ""
    for msg in state.get("chat_history", []):
        formatted_history += f"{msg['role'].upper()}: {msg['content']}\n"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an elite executive recruiter and career coach. Your job is to extract the candidate's resume into the JSON schema AND actively interview them to build a highly competitive, holistic profile.
         I want you to tell them what in their resume is good, and what can be better. This should go like a human conversation.

        CRITICAL DIRECTIVE: 
         0. You are provided with the 'Current JSON Profile'. You MUST preserve this data and UPDATE it with any new facts the user provides in the Chat History. Do not overwrite existing good data, only add to it.
         1. Do not just check for empty fields. Look deeply at the context of what they provided and identify what would make their profile stand out to top-tier companies.
         2. USE THE 'assistant_message' FIELD TO ACT LIKE A HUMAN.
         3. If the user asks a clarifying question (e.g., "Do you mean X or Y?"), YOU MUST ANSWER IT before asking your next question.
         4.  Acknowledge and validate their previous answer (e.g., "That's a great example of leadership. Now..."). 
         5. NEVER robotically repeat the same question if the user is asking for clarification.
         6. If the resume text includes an 'Extracted Links' section, use those URLs to populate personal_info.linkedin, personal_info.github, and personal_info.portfolio when applicable.
        
        Look for these holistic gaps:
        1. QUANTIFIABLE IMPACT: If they list a duty (e.g., "built a dashboard"), you MUST ask for the business impact or metrics (e.g., "How many users used it?" or "Did it save time/money?").
        2. LEADERSHIP & INITIATIVE: Ask if they mentored anyone, led any meetings, or pitched any ideas that were adopted.
        3. EXTRACURRICULARS & PROJECTS: If their profile is heavy on work but light on passion, ask about hackathons, open-source contributions, or personal side projects.
        4. TECHNICAL DEPTH: If they list a tool without context, ask how they applied it to solve a complex problem.

        If the profile lacks this depth, generate a question in 'assistant_message' and set 'is_complete' to False.

        RULES FOR ASKING QUESTIONS:
        1. ONE QUESTION AT A TIME: NEVER ask multiple questions at once.
        2. STRICT PRIORITIZATION: Ask the most crucial question first. Metrics/Impact on recent work is highest priority. Certifications/Links are lowest priority.
        3. COACHING TONE: Ask engaging, conversational questions. (e.g., "I see you used Python at your last job. What was the most complex problem you solved with it, and what was the result?")
        4. RESPECT NEGATIVES: If the user says they don't have something, DO NOT ask about it again.
         
        CRITICAL COUNTING DIRECTIVE:
        Evaluate the profile and estimate how many total missing gaps/questions remain. Output this exact number in 'remaining_questions_count'.

        Incorporate all new information from the chat history into the structured profile."""),
        (
            "user",
            "Original Resume Text:\n{resume_text}\n\nCurrent JSON Profile:\n{current_profile}\n\nChat History:\n{chat_history}",
        ),
    ])
    
    chain = prompt | structured_llm
    
    # Invoke the LLM with the current state
    result = chain.invoke({
        "resume_text": state["resume_text"],
        "current_profile": state.get("extracted_data") or {},
        "chat_history": formatted_history or "No chat yet."
    })
    # NEW
    questions_list = [result.assistant_message] if result.assistant_message else []
    
    # MUST RETURN A DICT UPDATING THE STATE KEYS
    # Using .model_dump() (or .dict() in Pydantic v1) converts the Pydantic object to a dictionary
    return {
        "extracted_data": result.profile.model_dump(),
        "pending_questions": questions_list,
        "remaining_questions": result.remaining_questions_count,
        "current_focus_field": result.current_focus_field,
        "is_complete": result.is_complete
    }

# 3. Define the Human Breakpoint Node
def human_input_node(state: AgentState):
    # LangGraph will pause BEFORE executing this node.
    pass

# 4. Define the Routing Logic
def should_continue(state: AgentState):
    if state.get("is_complete"):
        return END

    # If the LLM generated questions, route to human. Otherwise, finish.
    if not state.get("pending_questions") or not state["pending_questions"][0]:
        return END
    
    return "human_input"

# 5. Build and Compile the Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", process_resume_node)
workflow.add_node("human_input", human_input_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("human_input", "agent")

memory = InMemorySaver()
resume_agent_app = workflow.compile(checkpointer=memory, interrupt_before=["human_input"])
