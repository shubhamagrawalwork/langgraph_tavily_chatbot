import streamlit as st
import requests
import uuid
import json
from langchain_core.messages import HumanMessage, AIMessage

# **************************************** Constants and Config *************************
# Replace with your FastAPI URL.
API_BASE_URL = "https://langgraph-tavily-chatbot-v1-0-0.onrender.com/"

# **************************************** Utility Functions ****************************
def generate_thread_id():
    """Generates a new unique thread ID."""
    return str(uuid.uuid4())

def add_thread(thread_id):
    """Adds a new thread ID to the session state if it doesn't already exist."""
    if thread_id not in st.session_state['chat_threads']:
        st.session_state['chat_threads'].append(thread_id)

def reset_chat_and_session():
    """Resets the current chat session, creating a new thread."""
    st.session_state['thread_id'] = generate_thread_id()
    st.session_state['message_history'] = []
    add_thread(st.session_state['thread_id'])
    st.rerun()

def load_conversation(thread_id):
    """
    Retrieves and loads a conversation from the FastAPI backend.
    """
    try:
        response = requests.get(f"{API_BASE_URL}/history/{thread_id}")
        if response.status_code == 200:
            st.session_state['thread_id'] = thread_id
            st.session_state['message_history'] = response.json()
            st.rerun()
        else:
            st.error(f"Failed to load conversation for thread ID: {thread_id}")
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to backend: {e}")

# **************************************** Session Setup ******************************
if 'thread_id' not in st.session_state:
    st.session_state['thread_id'] = generate_thread_id()

if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []

if 'chat_threads' not in st.session_state:
    st.session_state['chat_threads'] = []
    
# Add the current thread to the list if it's new.
add_thread(st.session_state['thread_id'])

# **************************************** Sidebar UI *********************************
st.sidebar.title('LangGraph Chatbot')

if st.sidebar.button('New Chat'):
    reset_chat_and_session()

st.sidebar.header('My Conversations')

# Display chat thread buttons in the sidebar.
for thread_id in st.session_state['chat_threads'][::-1]:
    if st.sidebar.button(thread_id):
        # When a thread button is clicked, load that conversation.
        load_conversation(thread_id)

# **************************************** Main UI ************************************
st.title("LangGraph Chat with FastAPI Backend")

# Display conversation history.
for message in st.session_state['message_history']:
    with st.chat_message(message['role']):
        st.write(message['content'])

user_input = st.chat_input('Type here')

if user_input:
    # Append user message to history.
    st.session_state['message_history'].append({'role': 'user', 'content': user_input})
    with st.chat_message('user'):
        st.write(user_input)

    # Use a placeholder for the assistant's response to enable streaming.
    with st.chat_message('assistant'):
        placeholder = st.empty()
        full_response = ""

        try:
            # Make the streaming API call to the FastAPI backend.
            with requests.get(
                f"{API_BASE_URL}/chat?message={user_input}&thread_id={st.session_state['thread_id']}",
                stream=True,
                headers={"Accept": "text/event-stream"}
            ) as response:
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith('data:'):
                            data_str = decoded_line[5:].strip()
                            try:
                                event = json.loads(data_str)
                                if event['type'] == 'content':
                                    full_response += event['content']
                                    placeholder.write(full_response)
                                elif event['type'] == 'search_start':
                                    full_response += f"\n\nSearching for: {event['query']}..."
                                    placeholder.write(full_response)
                                elif event['type'] == 'search_results':
                                    # You can display these URLs nicely.
                                    urls = event['urls']
                                    full_response += f"\n\nFound some results: {', '.join(urls)}\n\n"
                                    placeholder.write(full_response)
                                elif event['type'] == 'end':
                                    break
                            except json.JSONDecodeError:
                                # Handle cases where data is not valid JSON.
                                pass
        except requests.exceptions.RequestException as e:
            placeholder.write(f"An error occurred: {e}")

        # Append the final full response to history.
        if full_response:
            st.session_state['message_history'].append({'role': 'assistant', 'content': full_response})