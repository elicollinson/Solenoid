# chart_generator_agent/agent.py
import logging
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from app.agent.models.factory import get_model
import yaml
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from app.agent.local_execution.adk_wrapper import ADKLocalWasmExecutor
from pathlib import Path
from google.genai import types

LOGGER = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
APP_ROOT = CURRENT_DIR.parent.parent.parent / "app"

# 2. Construct the path to the Wasm engine
WASM_PATH = APP_ROOT / "resources" / "python-wasi"

# 3. Initialize the Executor
secure_executor = ADKLocalWasmExecutor(wasm_path=str(WASM_PATH))

session_service = InMemorySessionService()

def load_mcp_toolsets(config_path="mcp_config.yaml"):
    """Load MCP toolsets from a YAML configuration file."""
    toolsets = []
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        if not config or "mcp_servers" not in config:
            LOGGER.warning(f"No 'mcp_servers' found in {config_path}")
            return []

        for server_name, server_config in config["mcp_servers"].items():
            LOGGER.info(f"Loading MCP server: {server_name}")
            try:
                toolset = McpToolset(
                    connection_params=StdioConnectionParams(
                        server_params=StdioServerParameters(
                            command=server_config["command"],
                            args=server_config["args"]
                        )
                    )
                )
                toolsets.append(toolset)
            except Exception as e:
                LOGGER.error(f"Failed to load MCP server {server_name}: {e}")
                
    except FileNotFoundError:
        LOGGER.warning(f"MCP config file not found at {config_path}")
    except Exception as e:
        LOGGER.error(f"Error loading MCP config: {e}")
        
    return toolsets

# 3. Define the Agent
agent = Agent(
    name="chart_generator_agent",
    model=get_model("agent"),
    instruction="""
    You are a Python Chart Generator Agent.
    
    YOUR GOAL: Create visualizations based on the user's request using the **Pygal** library.
    
    CRITICAL PROTOCOL:
    1.  RECEIVE REQUEST: Analyze the user's request for a chart/visualization.
    2.  WRITE CODE: Write Python code to generate the chart using **Pygal**.
        - **IMPORTANT**: You MUST save the output to a file named `chart.svg`.
        - **ONLY use Pygal**. Do not use Matplotlib, Altair, or other libraries.
        - **EXECUTION**: The code you write will be automatically executed by the system. You do not need to ask for permission.
    
    PYGAL DOCUMENTATION & EXAMPLES:
    
    **1. Basic Bar Chart**
    ```python
    import pygal
    bar_chart = pygal.Bar()
    bar_chart.title = 'Browser usage evolution (in %)'
    bar_chart.add('Firefox', [None, None, 0, 16.6, 25, 31, 36.4, 45.5, 46.3, 42.8, 37.1])
    bar_chart.add('Chrome',  [None, None, None, None, None, None,    0,  3.9, 10.8, 23.8, 35.3])
    bar_chart.render_to_file('chart.svg')
    print("Chart saved to chart.svg")
    ```

    **2. Line Chart**
    ```python
    import pygal
    line_chart = pygal.Line()
    line_chart.title = 'Browser usage evolution (in %)'
    line_chart.add('Firefox', [None, None, 0, 16.6, 25, 31, 36.4, 45.5, 46.3, 42.8, 37.1])
    line_chart.render_to_file('chart.svg')
    print("Chart saved to chart.svg")
    ```

    **3. Pie Chart**
    ```python
    import pygal
    pie_chart = pygal.Pie()
    pie_chart.title = 'Browser usage by version in February 2012 (in %)'
    pie_chart.add('IE', [5.7, 10.2, 2.6, 1])
    pie_chart.add('Firefox', [0.6, 16.8, 7.4, 2.2, 1.2, 1, 1, 1.1, 4.3, 1])
    pie_chart.render_to_file('chart.svg')
    print("Chart saved to chart.svg")
    ```

    **4. XY (Scatter) Chart**
    ```python
    import pygal
    xy_chart = pygal.XY(stroke=False)
    xy_chart.title = 'Correlation'
    xy_chart.add('A', [(0, 0), (.1, .2), (.3, .1), (.5, 1), (.8, .6), (1, 1.08), (1.3, 1.1), (2, 3.23), (2.43, 2)])
    xy_chart.render_to_file('chart.svg')
    print("Chart saved to chart.svg")
    ```

    **5. Styling**
    ```python
    from pygal.style import LightSolarizedStyle
    chart = pygal.Bar(style=LightSolarizedStyle)
    # ...
    ```

    3.  WAIT FOR OUTPUT: The system will execute your code and return the result.
    4.  ANALYZE OUTPUT: Check the "COMMAND OUTPUT" and "OUTPUT FILES".
    5.  FINAL ANSWER: Confirm the chart was generated and reference the file name.
    
    STOPPING CONDITION:
    - If you see "COMMAND OUTPUT" indicating success, you have ALREADY executed the code.
    - DO NOT re-execute the same code.
    - Just confirm the chart generation.
    """,
    tools=load_mcp_toolsets(),
    code_executor=secure_executor,
    # sub_agents=[code_executor_agent] # Removed to avoid multi-parent error
)

chart_generator_agent = agent
