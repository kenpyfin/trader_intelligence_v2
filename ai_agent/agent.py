#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import re

MAX_ATTEMPTS = 3


def read_memory(memory_file):
    """Reads the agent's memory file."""
    try:
        with open(memory_file, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Memory file not found. Starting with a blank slate."

def extract_files_from_message(message):
    """Extracts potential file paths from the message to pass to aider."""
    # This regex looks for words that look like file paths
    path_pattern = r'[\w\/\.-]+'
    words = re.findall(path_pattern, message)
    return [word for word in words if os.path.exists(word)]

def main():
    """Main function for the AI agent wrapper around aider."""
    parser = argparse.ArgumentParser(description="An AI agent that wraps the 'aider' CLI tool to enhance accuracy.")
    parser.add_argument('--message', type=str, required=True, help='The task for the agent to perform.')
    args = parser.parse_args()

    agent_dir = os.path.dirname(os.path.realpath(__file__))
    memory_file = os.path.join(agent_dir, 'memory.md')
    memory = read_memory(memory_file)

    print("--- AI Agent Initialized ---")
    print(f"Original Task: {args.message}")
    print("\n--- Reading from Memory ---")
    print(memory)

    files = extract_files_from_message(args.message)
    if files:
        print(f"\n--- Identified Files for Aider: {' '.join(files)} ---")
    else:
        print("\n--- No specific files identified; aider will run on the general context. ---")

    current_message = args.message

    for attempt in range(MAX_ATTEMPTS):
        print(f"\n--- Attempt {attempt + 1} of {MAX_ATTEMPTS} ---")
        
        command = ['aider', '--message', current_message] + files

        try:
            print(f"Executing command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            
            print("\n--- Aider Output ---")
            print(result.stdout)
            
            # Simple success check: if the command runs without error, assume success.
            print("\n--- Task Successfully Completed ---")
            return

        except FileNotFoundError:
            print("\n--- Error ---")
            print("The 'aider' command was not found. Please ensure it is installed and in your PATH.")
            return
        except subprocess.CalledProcessError as e:
            print("\n--- Aider Error ---")
            print(e.stdout)
            print(e.stderr)
            
            if attempt < MAX_ATTEMPTS - 1:
                print("\n--- Formulating New Request for Next Attempt ---")
                current_message = f"{args.message}. The previous attempt failed with the following error, please fix it: {e.stderr}"
            else:
                print("\n--- Max attempts reached. Task failed. ---")


if __name__ == "__main__":
    main()
