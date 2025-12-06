#!/usr/bin/env python3
"""
Evaluation Test Runner for General Local Agent

Runs all test cases from the CSV file, captures full conversation history,
and saves results to structured folders for LLM-as-judge evaluation.

Usage:
    poetry run python tests/eval/run_eval.py [--cases TC-001,TC-002] [--timeout 300]
"""

import os
import sys
import csv
import json
import yaml
import asyncio
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import the root agent (user_proxy_agent is the entry point)
from app.agent.prime_agent.user_proxy import root_agent
from app.agent.config import load_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)


def load_test_cases(csv_path: Path) -> list[dict]:
    """Load test cases from CSV file."""
    test_cases = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip empty rows
            if not row.get('test_id'):
                continue
            test_cases.append(row)
    return test_cases


def extract_prompts_from_settings(settings_path: Path) -> dict:
    """Extract agent_prompts section from app_settings.yaml."""
    with open(settings_path, 'r') as f:
        settings = yaml.safe_load(f)

    return {
        'agent_prompts': settings.get('agent_prompts', {}),
        'models': settings.get('models', {}),
        'mcp_servers': settings.get('mcp_servers', {}),
        'extracted_at': datetime.now().isoformat()
    }


def event_to_dict(event) -> dict:
    """Convert an ADK Event to a serializable dictionary."""
    result = {
        'id': event.id,
        'author': event.author,
        'timestamp': event.timestamp,
        'invocation_id': event.invocation_id,
        'turn_complete': event.turn_complete,
        'finish_reason': str(event.finish_reason) if event.finish_reason else None,
        'partial': event.partial,
        'error_code': event.error_code,
        'error_message': event.error_message,
    }

    # Extract content
    if event.content:
        content_data = {
            'role': event.content.role,
            'parts': []
        }
        if event.content.parts:
            for part in event.content.parts:
                part_data = {}
                if hasattr(part, 'text') and part.text:
                    part_data['text'] = part.text
                if hasattr(part, 'function_call') and part.function_call:
                    part_data['function_call'] = {
                        'name': part.function_call.name,
                        'args': dict(part.function_call.args) if part.function_call.args else {}
                    }
                if hasattr(part, 'function_response') and part.function_response:
                    part_data['function_response'] = {
                        'name': part.function_response.name,
                        'response': part.function_response.response
                    }
                if part_data:
                    content_data['parts'].append(part_data)
        result['content'] = content_data

    # Extract function calls
    try:
        function_calls = event.get_function_calls()
        if function_calls:
            result['function_calls'] = [
                {
                    'name': fc.name,
                    'args': dict(fc.args) if fc.args else {}
                }
                for fc in function_calls
            ]
    except Exception:
        pass

    # Extract function responses
    try:
        function_responses = event.get_function_responses()
        if function_responses:
            result['function_responses'] = [
                {
                    'name': fr.name,
                    'response': fr.response
                }
                for fr in function_responses
            ]
    except Exception:
        pass

    # Extract actions (agent transfers, etc.)
    if event.actions:
        actions_data = {}
        if hasattr(event.actions, 'transfer_to_agent') and event.actions.transfer_to_agent:
            actions_data['transfer_to_agent'] = event.actions.transfer_to_agent
        if hasattr(event.actions, 'escalate') and event.actions.escalate:
            actions_data['escalate'] = event.actions.escalate
        if hasattr(event.actions, 'skip_summarization') and event.actions.skip_summarization:
            actions_data['skip_summarization'] = event.actions.skip_summarization
        if actions_data:
            result['actions'] = actions_data

    return result


async def run_single_test(
    test_case: dict,
    app_name: str,
    timeout_seconds: int = 300
) -> dict:
    """Run a single test case and capture all conversation history."""
    test_id = test_case['test_id']
    test_prompt = test_case['test_prompt']

    LOGGER.info(f"Running test {test_id}: {test_case['test_name']}")

    # Create fresh session service for isolation
    session_service = InMemorySessionService()
    user_id = f"eval_user_{test_id}"
    session_id = f"eval_session_{test_id}_{datetime.now().strftime('%H%M%S')}"

    # Create session
    session = await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )

    # Create runner
    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service
    )

    # Prepare user message
    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=test_prompt)]
    )

    # Capture streaming events
    streaming_events = []
    final_response = None
    error_info = None
    start_time = datetime.now()

    try:
        # Run with timeout
        async def run_agent():
            nonlocal final_response
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_message
            ):
                streaming_events.append(event_to_dict(event))

                # Capture final response
                if hasattr(event, 'is_final_response') and event.is_final_response():
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                final_response = part.text
                                break

        await asyncio.wait_for(run_agent(), timeout=timeout_seconds)

    except asyncio.TimeoutError:
        error_info = f"Test timed out after {timeout_seconds} seconds"
        LOGGER.error(f"{test_id}: {error_info}")
    except Exception as e:
        error_info = f"Error during execution: {str(e)}"
        LOGGER.error(f"{test_id}: {error_info}", exc_info=True)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Get final session state with all events
    final_session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )

    # Build conversation history from session events
    conversation_history = []
    if final_session and final_session.events:
        for event in final_session.events:
            conversation_history.append(event_to_dict(event))

    # Compile result
    result = {
        'test_id': test_id,
        'test_name': test_case['test_name'],
        'category': test_case['category'],
        'test_prompt': test_prompt,
        'expected_behavior': test_case['expected_behavior'],
        'execution': {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'timeout_seconds': timeout_seconds,
            'error': error_info
        },
        'final_response': final_response,
        'conversation_history': conversation_history,
        'streaming_events_count': len(streaming_events),
        'streaming_events': streaming_events,
        'session_state': dict(final_session.state) if final_session else {},
        'metrics': {
            'metric_1': {'name': test_case.get('metric_1_name', ''), 'rubric': test_case.get('metric_1_rubric', '')},
            'metric_2': {'name': test_case.get('metric_2_name', ''), 'rubric': test_case.get('metric_2_rubric', '')},
            'metric_3': {'name': test_case.get('metric_3_name', ''), 'rubric': test_case.get('metric_3_rubric', '')},
            'metric_4': {'name': test_case.get('metric_4_name', ''), 'rubric': test_case.get('metric_4_rubric', '')},
            'metric_5': {'name': test_case.get('metric_5_name', ''), 'rubric': test_case.get('metric_5_rubric', '')},
        }
    }

    LOGGER.info(f"Completed {test_id} in {duration:.2f}s - {'SUCCESS' if not error_info else 'ERROR'}")

    return result


async def run_evaluation(
    test_cases: list[dict],
    output_dir: Path,
    timeout_seconds: int = 300
) -> dict:
    """Run all test cases and save results."""
    app_name = "AgentEvaluation"

    results_summary = {
        'run_id': output_dir.name,
        'start_time': datetime.now().isoformat(),
        'total_tests': len(test_cases),
        'completed': 0,
        'errors': 0,
        'test_results': []
    }

    for i, test_case in enumerate(test_cases, 1):
        test_id = test_case['test_id']
        LOGGER.info(f"Progress: {i}/{len(test_cases)} - {test_id}")

        try:
            result = await run_single_test(
                test_case=test_case,
                app_name=app_name,
                timeout_seconds=timeout_seconds
            )

            # Save individual test result
            result_file = output_dir / f"{test_id}.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)

            results_summary['completed'] += 1
            if result['execution']['error']:
                results_summary['errors'] += 1

            results_summary['test_results'].append({
                'test_id': test_id,
                'test_name': result['test_name'],
                'duration_seconds': result['execution']['duration_seconds'],
                'error': result['execution']['error'],
                'has_response': result['final_response'] is not None
            })

        except Exception as e:
            LOGGER.error(f"Failed to run {test_id}: {e}", exc_info=True)
            results_summary['errors'] += 1
            results_summary['test_results'].append({
                'test_id': test_id,
                'error': str(e)
            })

    results_summary['end_time'] = datetime.now().isoformat()

    return results_summary


def main():
    parser = argparse.ArgumentParser(description='Run agent evaluation test cases')
    parser.add_argument(
        '--cases',
        type=str,
        default=None,
        help='Comma-separated list of test case IDs to run (e.g., TC-001,TC-002). Runs all if not specified.'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Timeout in seconds for each test case (default: 300)'
    )
    parser.add_argument(
        '--csv',
        type=str,
        default=None,
        help='Path to test cases CSV file (default: tests/eval/agent_test_cases.csv)'
    )
    args = parser.parse_args()

    # Paths
    eval_dir = Path(__file__).parent
    csv_path = Path(args.csv) if args.csv else eval_dir / 'agent_test_cases.csv'
    settings_path = PROJECT_ROOT / 'app_settings.yaml'
    results_base_dir = eval_dir / 'eval_results'

    # Create timestamped run folder
    run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = results_base_dir / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info(f"Evaluation run directory: {run_dir}")

    # Load and filter test cases
    all_test_cases = load_test_cases(csv_path)
    LOGGER.info(f"Loaded {len(all_test_cases)} test cases from {csv_path}")

    if args.cases:
        selected_ids = set(args.cases.split(','))
        test_cases = [tc for tc in all_test_cases if tc['test_id'] in selected_ids]
        LOGGER.info(f"Filtered to {len(test_cases)} selected test cases: {selected_ids}")
    else:
        test_cases = all_test_cases

    if not test_cases:
        LOGGER.error("No test cases to run!")
        sys.exit(1)

    # Extract and save prompts from settings
    LOGGER.info("Extracting prompts from app_settings.yaml...")
    prompts_data = extract_prompts_from_settings(settings_path)
    prompts_file = run_dir / 'prompts.yaml'
    with open(prompts_file, 'w', encoding='utf-8') as f:
        yaml.dump(prompts_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    LOGGER.info(f"Saved prompts to {prompts_file}")

    # Also save a copy of the test cases used
    test_cases_file = run_dir / 'test_cases.json'
    with open(test_cases_file, 'w', encoding='utf-8') as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)
    LOGGER.info(f"Saved test cases to {test_cases_file}")

    # Run evaluation
    LOGGER.info(f"Starting evaluation of {len(test_cases)} test cases...")
    results_summary = asyncio.run(run_evaluation(
        test_cases=test_cases,
        output_dir=run_dir,
        timeout_seconds=args.timeout
    ))

    # Save summary
    summary_file = run_dir / 'summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n" + "="*60)
    print("EVALUATION COMPLETE")
    print("="*60)
    print(f"Run ID: {results_summary['run_id']}")
    print(f"Total tests: {results_summary['total_tests']}")
    print(f"Completed: {results_summary['completed']}")
    print(f"Errors: {results_summary['errors']}")
    print(f"Results saved to: {run_dir}")
    print("="*60)

    # Print individual test results
    print("\nTest Results:")
    for tr in results_summary['test_results']:
        status = "✓" if not tr.get('error') else "✗"
        duration = tr.get('duration_seconds', 0)
        print(f"  {status} {tr['test_id']}: {duration:.2f}s")
        if tr.get('error'):
            print(f"      Error: {tr['error'][:80]}...")

    return 0 if results_summary['errors'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
