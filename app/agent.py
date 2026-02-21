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

# 2. Define the AI Node
def process_resume_node(state: AgentState):
    # Initialize the LLM (Requires OPENAI_API_KEY in your docker-compose environment)
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Force the LLM to output the exact Pydantic schema we defined
    structured_llm = llm.with_structured_output(schemas.ExtractionResult)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert technical recruiter conducting a conversational interview. 
        Extract the candidate's resume into the exact JSON schema provided. 
        
        If critical information is missing, generate specific questions in 'missing_info_questions'. 
        
        CRITICAL RULES FOR ASKING QUESTIONS:
        1. 1. ONE QUESTION AT A TIME: You MUST ask ONLY ONE single question per turn. Never output a list of questions. Wait for the user to answer the current question before moving to the next missing piece of information.
        2. NEVER use robotic phrasing or refer to JSON keys directly (e.g., NEVER ask "What is the experience context for...").
        3. Ask natural, conversational questions.   
           - Bad: "What is the experience context for Accenture Strategy?"
           - Good: "Could you tell me a bit more about the overarching business problem you were solving during your time at Accenture Strategy?"
           - Bad: "Provide metrics for Nectorr Labs."
           - Good: "What was the quantifiable impact or main result of your work at Nectorr Labs?"
        4. Do not ask for more than 3 missing things at once to avoid overwhelming the candidate. Prioritize the most recent or relevant roles first.

        Incorporate any new information from the chat history into the profile."""),
        ("user", "Original Resume Text:\n{resume_text}\n\nChat History (Answers from user):\n{chat_history}")
    ])
    
    chain = prompt | structured_llm
    
    # Invoke the LLM with the current state
    result = chain.invoke({
        "resume_text": state["resume_text"],
        "chat_history": state["chat_history"]
    })
    questions_list = [result.next_question] if result.next_question else []
    
    # MUST RETURN A DICT UPDATING THE STATE KEYS
    # Using .model_dump() (or .dict() in Pydantic v1) converts the Pydantic object to a dictionary
    return {
        "extracted_data": result.profile.model_dump(),
        "pending_questions": questions_list
    }

# 3. Define the Human Breakpoint Node
def human_input_node(state: AgentState):
    # LangGraph will pause BEFORE executing this node.
    pass

# 4. Define the Routing Logic
def should_continue(state: AgentState):
    # If the LLM generated questions, route to human. Otherwise, finish.
    if not state.get("pending_questions"):
        return END

    chat_history = state.get("chat_history", [])
    questions_asked_so_far = sum(1 for msg in chat_history if msg["role"] == "assistant")
    
    # If it has already asked 3 questions, and is trying to ask a 4th, cut it off!
    if questions_asked_so_far >= 3:
        # Returning END forces the graph to finish and output the current JSON
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