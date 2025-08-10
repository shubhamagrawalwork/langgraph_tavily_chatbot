from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from typing import Optional, TypedDict, Annotated, List, Dict, Any
from langgraph.checkpoint.memory import MemorySaver

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse

import asyncio
import json
import uuid

load_dotenv()

memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

search_tool = TavilySearch(
    max_results=4,
)

tools = [search_tool]

llm = ChatOpenAI(model="gpt-4o")

llm_with_tools = llm.bind_tools(tools=tools,tool_choice="auto")

async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {
        "messages": [result], 
    }

async def tools_router(state: State):
    last_message = state["messages"][-1]

    if(hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0):
        return "tool_node"
    else: 
        return END
    
async def tool_node(state):
    """Custom tool node that handles tool calls from the LLM."""
    tool_calls = state["messages"][-1].tool_calls
    
    tool_messages = []
    
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        if tool_name == "tavily_search":
            search_results = await search_tool.ainvoke(tool_args)
            
            tool_message = ToolMessage(
                content=str(search_results),
                tool_call_id=tool_id,
                name=tool_name
            )
            
            tool_messages.append(tool_message)
    
    return {"messages": tool_messages}

graph_builder = StateGraph(State)

graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")

graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")

chatbot = graph_builder.compile(checkpointer=memory)










app = FastAPI()

def generate_unique_id():
    return str(uuid.uuid4())


def serialise_ai_message_chunk(chunk):
    if(isinstance(chunk, AIMessageChunk)):
        return chunk.content
    else:
        raise TypeError(
            f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
        )

async def generate_chat_responses(message: str, thread_id: str):
   
    CONFIG = {'configurable': {'thread_id': thread_id}}
    
    events = chatbot.astream_events( {"messages": [HumanMessage(content=message)]}, version="v2", config=CONFIG)
    
    async for event in events:
        event_type = event["event"]
        
        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            safe_content = chunk_content.replace("'", "\\'").replace("\n", "\\n")
            yield f"data: {{\"type\": \"content\", \"content\": \"{safe_content}\"}}\n\n"
            
        elif event_type == "on_chat_model_end":
            tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]
            
            if search_calls:
                search_query = search_calls[0]["args"].get("query", "")
                safe_query = search_query.replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
                yield f"data: {{\"type\": \"search_start\", \"query\": \"{safe_query}\"}}\n\n"
                
        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            output = event["data"]["output"]
            if isinstance(output, list):
                urls = []
                for item in output:
                    if isinstance(item, dict) and "url" in item:
                        urls.append(item["url"])
                urls_json = json.dumps(urls)
                yield f"data: {{\"type\": \"search_results\", \"urls\": {urls_json}}}\n\n"
    
    yield f"data: {{\"type\": \"end\"}}\n\n"


@app.get("/chat", response_class=StreamingResponse)
async def chat(message: str = Query(...), thread_id: str = Query(...)):
    """
    Endpoint to handle chat messages and return streaming responses.
    """
    response_generator = generate_chat_responses(message, thread_id)
    return StreamingResponse(response_generator, media_type="text/event-stream")


@app.get("/history/{thread_id}", response_model=List[Dict[str, Any]])
async def get_history(thread_id: str):
    """
    Endpoint to retrieve the full conversation history for a given thread_id.
    """
    try:
        state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
        messages = state.values['messages']
        
        history = []
        for msg in messages:
            role = 'user' if isinstance(msg, HumanMessage) else 'assistant'
            history.append({'role': role, 'content': msg.content})
            
        return history
    except Exception as e:
        return []






