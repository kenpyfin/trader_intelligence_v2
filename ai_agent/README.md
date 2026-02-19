# AI Coding Agent

This is an AI coding agent that acts as an intelligent wrapper for the `aider` CLI tool. It enhances `aider` by providing an automated feedback loop. If a command fails, the agent analyzes the error and re-runs the command with a refined prompt to correct the mistake.

## Usage

To run the agent, make sure it is executable:

```bash
chmod +x agent.py
```

Then, you can invoke it from the command line. The agent will automatically detect file paths in your message and pass them to `aider`.

If `aider` encounters an error, the agent will automatically try again up to two more times, each time providing the error context back to `aider` to improve the chances of success.

### Example

```bash
./agent.py --message "Implement a new data validation function in backend/src/analytics/validation.py"
```

## Memory

The `memory.md` file provides the agent with long-term context and guiding principles. You can edit this file to give the agent more specific instructions or to update its core objectives.
