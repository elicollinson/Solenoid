
from google.adk.agents import Agent
import inspect

with open("agent_details.txt", "w") as f:
    f.write(f"Agent init signature: {inspect.signature(Agent.__init__)}\n")
    f.write(f"Agent methods: {dir(Agent)}\n")
