import os
import json
import asyncio
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
from src.server import call_tool as mcp_call_tool

Path("generated_datasets").mkdir(exist_ok=True)


async def call_mcp(tool_name, arguments):
    """Call MCP server tool."""
    try:
        result = await mcp_call_tool(tool_name, arguments)
        return result[0].text if result else "No response"
    except Exception as e:
        return f"Error: {str(e)}"


def process(message):
    """Process message using MCP tools."""
    try:
        msg_lower = message.lower()
        
        if "search" in msg_lower and "dataset" in msg_lower:
            query = message.replace("search", "").replace("dataset", "").replace("datasets", "").strip()
            return asyncio.run(call_mcp("search_datasets", {"query": query, "limit": 10}))
        
        elif "help" in msg_lower:
            return asyncio.run(call_mcp("geocr_help", {}))
        
        elif "code" in msg_lower or "pytorch" in msg_lower:
            return asyncio.run(call_mcp("geocr_builder_context", {}))
        
        else:
            return asyncio.run(call_mcp("geocr_help", {}))
    
    except Exception as e:
        return f"Error: {str(e)}"


with gr.Blocks(title="GeoCR MCP") as app:
    gr.Markdown("# GeoCR MCP\nGeospatial ML Dataset Assistant")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Metadata")
            metadata_view = gr.JSON(label="GeoCroissant Metadata")
            notebook_file = gr.File(label="Generated Notebook")
        
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=500)
            msg = gr.Textbox(label="Message", placeholder="Type your request...")
            
            with gr.Row():
                submit = gr.Button("Send", variant="primary")
                clear = gr.Button("Clear")
            
            gr.Examples(
                examples=[
                    "Search flood datasets",
                    "Show me PyTorch code examples",
                    "Help",
                ],
                inputs=msg
            )
    
    def respond(message, chat_history):
        response = process(message)
        chat_history.append((message, response))
        
        json_files = list(Path("generated_datasets").glob("*.json"))
        notebook_files = list(Path("generated_datasets").glob("*.ipynb"))
        
        metadata = None
        notebook = None
        
        if json_files:
            with open(json_files[-1]) as f:
                metadata = json.load(f)
        
        if notebook_files:
            notebook = str(notebook_files[-1])
        
        return "", chat_history, metadata, notebook
    
    msg.submit(respond, [msg, chatbot], [msg, chatbot, metadata_view, notebook_file])
    submit.click(respond, [msg, chatbot], [msg, chatbot, metadata_view, notebook_file])
    clear.click(lambda: (None, None, None), None, [chatbot, metadata_view, notebook_file])


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7860)
