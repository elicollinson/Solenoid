#!/usr/bin/env python3
"""
Evaluation Test Runner for General Local Agent

Runs all test cases from the CSV file, captures full conversation history,
grades outputs using LLM-as-judge, and saves results to structured folders.

Supports multiple sequential runs with aggregated scoring for statistical reliability.

Usage:
    poetry run python tests/eval/run_eval.py [--cases TC-001,TC-002] [--timeout 300] [--skip-grading]
    poetry run python tests/eval/run_eval.py --runs 3  # Run 3 times and aggregate scores
"""

import os
import sys
import csv
import json
import yaml
import asyncio
import logging
import argparse
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
import litellm

# Import the root agent (user_proxy_agent is the entry point)
from app.agent.prime_agent.user_proxy import root_agent
from app.agent.config import load_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)

# Grading model configuration
GRADING_MODEL = "ollama_chat/gpt-oss:20b"


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


def format_conversation_for_grading(conversation_history: list[dict]) -> str:
    """Format conversation history into a readable string for grading."""
    lines = []
    for event in conversation_history:
        author = event.get('author', 'unknown')
        content = event.get('content', {})
        parts = content.get('parts', [])

        for part in parts:
            if 'text' in part:
                lines.append(f"[{author}]: {part['text']}")
            if 'function_call' in part:
                fc = part['function_call']
                lines.append(f"[{author}] TOOL CALL: {fc['name']}({json.dumps(fc.get('args', {}))})")
            if 'function_response' in part:
                fr = part['function_response']
                response_str = json.dumps(fr.get('response', {}), default=str)[:500]
                lines.append(f"[{author}] TOOL RESPONSE ({fr['name']}): {response_str}")

        # Show agent transfers
        actions = event.get('actions', {})
        if 'transfer_to_agent' in actions:
            lines.append(f"[{author}] TRANSFER TO: {actions['transfer_to_agent']}")

    return "\n".join(lines)


def build_grading_prompt(test_result: dict) -> str:
    """Build the prompt for LLM-as-judge grading."""
    metrics = test_result.get('metrics', {})

    # Build metrics section
    metrics_section = []
    for i in range(1, 6):
        metric = metrics.get(f'metric_{i}', {})
        name = metric.get('name', '')
        rubric = metric.get('rubric', '')
        if name and rubric:
            metrics_section.append(f"""
METRIC {i}: {name}
RUBRIC: {rubric}
""")

    metrics_text = "\n".join(metrics_section) if metrics_section else "No metrics defined."

    # Format conversation
    conversation_text = format_conversation_for_grading(
        test_result.get('conversation_history', [])
    )

    # Truncate if too long
    if len(conversation_text) > 8000:
        conversation_text = conversation_text[:8000] + "\n... [TRUNCATED]"

    prompt = f"""You are an expert evaluator grading an AI agent system's performance on a test case.

## TEST CASE INFORMATION

**Test ID**: {test_result.get('test_id', 'Unknown')}
**Test Name**: {test_result.get('test_name', 'Unknown')}
**Category**: {test_result.get('category', 'Unknown')}

**User Prompt**:
{test_result.get('test_prompt', 'No prompt')}

**Expected Behavior**:
{test_result.get('expected_behavior', 'No expected behavior specified')}

**Execution Error** (if any):
{test_result.get('execution', {}).get('error', 'None')}

**Final Response**:
{test_result.get('final_response', 'No response')}

## FULL CONVERSATION HISTORY

{conversation_text}

## METRICS TO EVALUATE

{metrics_text}

## YOUR TASK

Evaluate the agent's performance on each metric using the provided rubrics. Each metric uses a 1-5 scale where:
- 1 = Poor/Failed
- 2 = Below expectations
- 3 = Meets basic expectations
- 4 = Good performance
- 5 = Excellent performance

You MUST respond with ONLY a valid JSON object in this exact format (no other text before or after):

```json
{{
  "grades": {{
    "metric_1": {{
      "score": <1-5>,
      "justification": "<brief 1-2 sentence explanation>"
    }},
    "metric_2": {{
      "score": <1-5>,
      "justification": "<brief 1-2 sentence explanation>"
    }},
    "metric_3": {{
      "score": <1-5>,
      "justification": "<brief 1-2 sentence explanation>"
    }},
    "metric_4": {{
      "score": <1-5>,
      "justification": "<brief 1-2 sentence explanation>"
    }},
    "metric_5": {{
      "score": <1-5 or null if metric not applicable>,
      "justification": "<brief explanation or null>"
    }}
  }},
  "overall_notes": "<1-2 sentences summarizing overall performance>"
}}
```

If a metric has no name/rubric defined, set its score to null.

Respond with ONLY the JSON object, no additional text."""

    return prompt


def extract_json_from_response(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    matches = re.findall(code_block_pattern, text, re.DOTALL)

    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Try to find raw JSON object
    json_pattern = r'\{[\s\S]*\}'
    matches = re.findall(json_pattern, text)

    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    # Last resort: try parsing the whole thing
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


async def grade_test_result(test_result: dict, max_retries: int = 3) -> dict:
    """Grade a test result using LLM-as-judge."""
    prompt = build_grading_prompt(test_result)

    for attempt in range(max_retries):
        try:
            LOGGER.info(f"Grading {test_result.get('test_id')} (attempt {attempt + 1}/{max_retries})")

            response = await litellm.acompletion(
                model=GRADING_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert AI evaluator. You respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent grading
                num_ctx=16000,
            )

            response_text = response.choices[0].message.content

            # Parse the JSON response
            grades = extract_json_from_response(response_text)

            if grades and 'grades' in grades:
                LOGGER.info(f"Successfully graded {test_result.get('test_id')}")
                return {
                    'success': True,
                    'grades': grades.get('grades', {}),
                    'overall_notes': grades.get('overall_notes', ''),
                    'raw_response': response_text,
                    'attempt': attempt + 1
                }
            else:
                LOGGER.warning(f"Invalid JSON structure in grading response (attempt {attempt + 1})")

        except Exception as e:
            LOGGER.error(f"Grading error (attempt {attempt + 1}): {e}")

    # Return failure after all retries
    return {
        'success': False,
        'grades': {},
        'overall_notes': 'Grading failed after all retries',
        'raw_response': None,
        'attempt': max_retries
    }


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


def build_final_summary_prompt(results_summary: dict) -> str:
    """Build prompt for final summary analysis."""
    # Build a table of results
    results_table = []
    for tr in results_summary.get('test_results', []):
        row = {
            'test_id': tr.get('test_id'),
            'category': tr.get('category', 'Unknown'),
            'test_name': tr.get('test_name', 'Unknown'),
            'error': tr.get('error'),
            'avg_score': tr.get('avg_score'),
            'scores': tr.get('scores', {}),
            'notes': tr.get('overall_notes', '')
        }
        results_table.append(row)

    results_json = json.dumps(results_table, indent=2, default=str)

    prompt = f"""You are an expert evaluator analyzing the results of an AI agent system evaluation.

## EVALUATION SUMMARY

**Run ID**: {results_summary.get('run_id', 'Unknown')}
**Total Tests**: {results_summary.get('total_tests', 0)}
**Completed**: {results_summary.get('completed', 0)}
**Errors**: {results_summary.get('errors', 0)}

## TEST RESULTS

{results_json}

## YOUR TASK

Analyze these evaluation results and provide a comprehensive summary. Your analysis should include:

1. **Overall Performance**: How well did the agent system perform overall?
2. **Strengths**: What did the agent system do well? Which categories or capabilities showed strong performance?
3. **Weaknesses**: Where did the agent system struggle? What patterns of failure emerged?
4. **Category Analysis**: Break down performance by test category (Routing Decision, Planning Quality, Error Handling, etc.)
5. **Critical Issues**: Are there any critical bugs or failures that need immediate attention?
6. **Recommendations**: What specific improvements would have the biggest impact?

Respond with a JSON object in this exact format:

```json
{{
  "overall_score": <average score across all tests, 1-5 scale>,
  "performance_summary": "<2-3 sentence overall assessment>",
  "strengths": [
    "<strength 1>",
    "<strength 2>"
  ],
  "weaknesses": [
    "<weakness 1>",
    "<weakness 2>"
  ],
  "category_breakdown": {{
    "<category name>": {{
      "avg_score": <number>,
      "test_count": <number>,
      "assessment": "<1 sentence assessment>"
    }}
  }},
  "critical_issues": [
    "<critical issue if any, or empty array>"
  ],
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "area": "<area to improve>",
      "suggestion": "<specific suggestion>"
    }}
  ],
  "detailed_analysis": "<2-3 paragraph detailed analysis>"
}}
```

Respond with ONLY the JSON object."""

    return prompt


async def generate_final_summary(results_summary: dict) -> dict:
    """Generate a final summary analysis using LLM."""
    prompt = build_final_summary_prompt(results_summary)

    for attempt in range(3):
        try:
            LOGGER.info(f"Generating final summary (attempt {attempt + 1}/3)")

            response = await litellm.acompletion(
                model=GRADING_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert AI evaluator. You respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                num_ctx=16000,
            )

            response_text = response.choices[0].message.content
            summary = extract_json_from_response(response_text)

            if summary and 'performance_summary' in summary:
                LOGGER.info("Successfully generated final summary")
                return {
                    'success': True,
                    'analysis': summary,
                    'raw_response': response_text
                }
            else:
                LOGGER.warning(f"Invalid summary structure (attempt {attempt + 1})")

        except Exception as e:
            LOGGER.error(f"Summary generation error (attempt {attempt + 1}): {e}")

    return {
        'success': False,
        'analysis': {},
        'raw_response': None
    }


def save_aggregated_scores(results_summary: dict, output_dir: Path):
    """Save aggregated scores to CSV and JSON files."""
    # Prepare data for CSV
    csv_rows = []
    for tr in results_summary.get('test_results', []):
        row = {
            'test_id': tr.get('test_id', ''),
            'category': tr.get('category', ''),
            'test_name': tr.get('test_name', ''),
            'duration_seconds': tr.get('duration_seconds', 0),
            'error': 'Yes' if tr.get('error') else 'No',
            'avg_score': tr.get('avg_score', ''),
        }

        # Add individual metric scores
        scores = tr.get('scores', {})
        for i in range(1, 6):
            metric_key = f'metric_{i}'
            row[f'score_m{i}'] = scores.get(metric_key, '')

        row['notes'] = tr.get('overall_notes', '')[:200]  # Truncate notes
        csv_rows.append(row)

    # Save as CSV
    csv_file = output_dir / 'scores.csv'
    if csv_rows:
        fieldnames = ['test_id', 'category', 'test_name', 'duration_seconds', 'error',
                      'avg_score', 'score_m1', 'score_m2', 'score_m3', 'score_m4', 'score_m5', 'notes']
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        LOGGER.info(f"Saved aggregated scores to {csv_file}")

    # Save detailed JSON aggregation
    json_file = output_dir / 'scores.json'
    aggregation = {
        'run_id': results_summary.get('run_id'),
        'timestamp': datetime.now().isoformat(),
        'summary_stats': {},
        'category_stats': {},
        'test_scores': []
    }

    # Calculate summary statistics
    all_scores = []
    category_scores = {}
    for tr in results_summary.get('test_results', []):
        category = tr.get('category', 'Unknown')
        avg_score = tr.get('avg_score')

        if avg_score is not None:
            all_scores.append(avg_score)
            if category not in category_scores:
                category_scores[category] = []
            category_scores[category].append(avg_score)

        aggregation['test_scores'].append({
            'test_id': tr.get('test_id'),
            'category': category,
            'test_name': tr.get('test_name'),
            'avg_score': avg_score,
            'scores': tr.get('scores', {}),
            'error': tr.get('error'),
            'notes': tr.get('overall_notes', '')
        })

    # Summary stats
    if all_scores:
        aggregation['summary_stats'] = {
            'total_tests': len(results_summary.get('test_results', [])),
            'tests_graded': len(all_scores),
            'overall_avg': round(sum(all_scores) / len(all_scores), 2),
            'min_score': min(all_scores),
            'max_score': max(all_scores),
            'tests_with_errors': results_summary.get('errors', 0)
        }

    # Category stats
    for category, scores in category_scores.items():
        aggregation['category_stats'][category] = {
            'test_count': len(scores),
            'avg_score': round(sum(scores) / len(scores), 2),
            'min_score': min(scores),
            'max_score': max(scores)
        }

    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(aggregation, f, indent=2, ensure_ascii=False)
    LOGGER.info(f"Saved detailed score aggregation to {json_file}")

    return aggregation


def aggregate_multi_run_results(all_run_results: list[dict], output_dir: Path) -> dict:
    """
    Aggregate results across multiple evaluation runs.

    Returns a dictionary with:
    - Per-test-case mean, std dev, min, max across runs
    - Per-metric aggregated statistics
    - Overall aggregated statistics
    - Per-category aggregated statistics
    """
    if not all_run_results:
        return {}

    num_runs = len(all_run_results)

    # Collect scores per test case across all runs
    test_scores_by_id = {}  # test_id -> {metric_name -> [scores across runs]}
    test_avg_scores_by_id = {}  # test_id -> [avg_scores across runs]
    test_metadata = {}  # test_id -> {name, category}

    for run_result in all_run_results:
        for test_result in run_result.get('test_results', []):
            test_id = test_result.get('test_id')
            if not test_id:
                continue

            # Store metadata
            if test_id not in test_metadata:
                test_metadata[test_id] = {
                    'test_name': test_result.get('test_name', 'Unknown'),
                    'category': test_result.get('category', 'Unknown')
                }

            # Initialize tracking structures
            if test_id not in test_scores_by_id:
                test_scores_by_id[test_id] = {}
            if test_id not in test_avg_scores_by_id:
                test_avg_scores_by_id[test_id] = []

            # Collect per-metric scores
            scores = test_result.get('scores', {})
            for metric_key, score in scores.items():
                if score is not None and isinstance(score, (int, float)):
                    if metric_key not in test_scores_by_id[test_id]:
                        test_scores_by_id[test_id][metric_key] = []
                    test_scores_by_id[test_id][metric_key].append(score)

            # Collect average scores
            avg_score = test_result.get('avg_score')
            if avg_score is not None:
                test_avg_scores_by_id[test_id].append(avg_score)

    # Build aggregated results per test case
    aggregated_tests = []
    all_mean_scores = []
    category_scores = {}  # category -> [mean_scores]

    for test_id, metric_scores in test_scores_by_id.items():
        metadata = test_metadata.get(test_id, {})
        category = metadata.get('category', 'Unknown')

        test_agg = {
            'test_id': test_id,
            'test_name': metadata.get('test_name', 'Unknown'),
            'category': category,
            'runs_with_scores': len(test_avg_scores_by_id.get(test_id, [])),
            'metrics': {}
        }

        # Aggregate per-metric scores
        for metric_key, scores in metric_scores.items():
            if scores:
                test_agg['metrics'][metric_key] = {
                    'mean': round(statistics.mean(scores), 2),
                    'std_dev': round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
                    'min': min(scores),
                    'max': max(scores),
                    'count': len(scores)
                }

        # Aggregate overall test scores
        avg_scores = test_avg_scores_by_id.get(test_id, [])
        if avg_scores:
            mean_score = statistics.mean(avg_scores)
            test_agg['overall'] = {
                'mean': round(mean_score, 2),
                'std_dev': round(statistics.stdev(avg_scores), 2) if len(avg_scores) > 1 else 0.0,
                'min': round(min(avg_scores), 2),
                'max': round(max(avg_scores), 2),
                'count': len(avg_scores)
            }
            all_mean_scores.append(mean_score)

            # Track category scores
            if category not in category_scores:
                category_scores[category] = []
            category_scores[category].append(mean_score)

        aggregated_tests.append(test_agg)

    # Sort by test_id
    aggregated_tests.sort(key=lambda x: x['test_id'])

    # Build category aggregation
    category_aggregation = {}
    for category, scores in category_scores.items():
        if scores:
            category_aggregation[category] = {
                'mean': round(statistics.mean(scores), 2),
                'std_dev': round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
                'min': round(min(scores), 2),
                'max': round(max(scores), 2),
                'test_count': len(scores)
            }

    # Build final aggregation structure
    aggregation = {
        'multi_run_info': {
            'total_runs': num_runs,
            'run_ids': [r.get('run_id', 'Unknown') for r in all_run_results],
            'aggregation_timestamp': datetime.now().isoformat()
        },
        'overall_statistics': {},
        'category_statistics': category_aggregation,
        'test_statistics': aggregated_tests
    }

    # Overall statistics
    if all_mean_scores:
        aggregation['overall_statistics'] = {
            'mean': round(statistics.mean(all_mean_scores), 2),
            'std_dev': round(statistics.stdev(all_mean_scores), 2) if len(all_mean_scores) > 1 else 0.0,
            'min': round(min(all_mean_scores), 2),
            'max': round(max(all_mean_scores), 2),
            'tests_scored': len(all_mean_scores)
        }

    # Save aggregated results
    agg_file = output_dir / 'multi_run_aggregation.json'
    with open(agg_file, 'w', encoding='utf-8') as f:
        json.dump(aggregation, f, indent=2, ensure_ascii=False)
    LOGGER.info(f"Saved multi-run aggregation to {agg_file}")

    # Save CSV summary
    csv_file = output_dir / 'multi_run_scores.csv'
    csv_rows = []
    for test in aggregated_tests:
        row = {
            'test_id': test['test_id'],
            'test_name': test['test_name'],
            'category': test['category'],
            'runs': test.get('runs_with_scores', 0),
            'mean_score': test.get('overall', {}).get('mean', ''),
            'std_dev': test.get('overall', {}).get('std_dev', ''),
            'min_score': test.get('overall', {}).get('min', ''),
            'max_score': test.get('overall', {}).get('max', '')
        }
        csv_rows.append(row)

    if csv_rows:
        fieldnames = ['test_id', 'test_name', 'category', 'runs', 'mean_score', 'std_dev', 'min_score', 'max_score']
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        LOGGER.info(f"Saved multi-run scores CSV to {csv_file}")

    return aggregation


async def run_evaluation(
    test_cases: list[dict],
    output_dir: Path,
    timeout_seconds: int = 300,
    skip_grading: bool = False
) -> dict:
    """Run all test cases, grade them, and save results."""
    app_name = "AgentEvaluation"

    results_summary = {
        'run_id': output_dir.name,
        'start_time': datetime.now().isoformat(),
        'total_tests': len(test_cases),
        'completed': 0,
        'errors': 0,
        'grading_enabled': not skip_grading,
        'test_results': []
    }

    for i, test_case in enumerate(test_cases, 1):
        test_id = test_case['test_id']
        LOGGER.info(f"Progress: {i}/{len(test_cases)} - {test_id}")

        try:
            # Run the test
            result = await run_single_test(
                test_case=test_case,
                app_name=app_name,
                timeout_seconds=timeout_seconds
            )

            # Grade the result if enabled
            if not skip_grading:
                grading_result = await grade_test_result(result)
                result['grading'] = grading_result
            else:
                result['grading'] = {'success': False, 'grades': {}, 'overall_notes': 'Grading skipped'}

            # Save individual test result
            result_file = output_dir / f"{test_id}.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)

            results_summary['completed'] += 1
            if result['execution']['error']:
                results_summary['errors'] += 1

            # Build summary entry
            summary_entry = {
                'test_id': test_id,
                'test_name': result['test_name'],
                'category': result['category'],
                'duration_seconds': result['execution']['duration_seconds'],
                'error': result['execution']['error'],
                'has_response': result['final_response'] is not None,
            }

            # Add grading scores to summary
            if result.get('grading', {}).get('success'):
                grades = result['grading'].get('grades', {})
                scores = {}
                for metric_key, metric_data in grades.items():
                    if isinstance(metric_data, dict) and metric_data.get('score') is not None:
                        scores[metric_key] = metric_data['score']
                summary_entry['scores'] = scores
                summary_entry['overall_notes'] = result['grading'].get('overall_notes', '')

                # Calculate average score
                valid_scores = [s for s in scores.values() if isinstance(s, (int, float))]
                if valid_scores:
                    summary_entry['avg_score'] = round(sum(valid_scores) / len(valid_scores), 2)

            results_summary['test_results'].append(summary_entry)

        except Exception as e:
            LOGGER.error(f"Failed to run {test_id}: {e}", exc_info=True)
            results_summary['errors'] += 1
            results_summary['test_results'].append({
                'test_id': test_id,
                'error': str(e)
            })

    results_summary['end_time'] = datetime.now().isoformat()

    # Save aggregated scores
    LOGGER.info("Saving aggregated scores...")
    aggregation = save_aggregated_scores(results_summary, output_dir)
    results_summary['aggregation'] = aggregation.get('summary_stats', {})

    # Generate final summary analysis if grading was enabled
    if not skip_grading and results_summary['completed'] > 0:
        LOGGER.info("Generating final summary analysis...")
        final_summary = await generate_final_summary(results_summary)
        results_summary['final_analysis'] = final_summary

        # Save final analysis separately
        analysis_file = output_dir / 'final_analysis.json'
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(final_summary, f, indent=2, ensure_ascii=False)
        LOGGER.info(f"Saved final analysis to {analysis_file}")

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
    parser.add_argument(
        '--skip-grading',
        action='store_true',
        help='Skip LLM-as-judge grading step'
    )
    parser.add_argument(
        '--runs', '-n',
        type=int,
        default=1,
        help='Number of sequential evaluation runs to perform (default: 1). Multiple runs are aggregated for statistical reliability.'
    )
    args = parser.parse_args()

    # Paths
    eval_dir = Path(__file__).parent
    csv_path = Path(args.csv) if args.csv else eval_dir / 'agent_test_cases.csv'
    settings_path = PROJECT_ROOT / 'app_settings.yaml'
    results_base_dir = eval_dir / 'eval_results'

    # Handle multi-run setup
    num_runs = args.runs
    if num_runs < 1:
        LOGGER.error("Number of runs must be at least 1")
        sys.exit(1)

    # Create batch directory for multi-run or single run folder
    batch_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if num_runs > 1:
        batch_dir = results_base_dir / f"batch_{batch_timestamp}_{num_runs}runs"
        batch_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info(f"Multi-run batch directory: {batch_dir}")
        LOGGER.info(f"Running {num_runs} sequential evaluation runs...")
    else:
        batch_dir = results_base_dir
        LOGGER.info("Running single evaluation...")

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

    # Extract prompts from settings (for saving with results)
    LOGGER.info("Extracting prompts from app_settings.yaml...")
    prompts_data = extract_prompts_from_settings(settings_path)

    # Save prompts to batch directory if multi-run
    if num_runs > 1:
        prompts_file = batch_dir / 'prompts.yaml'
        with open(prompts_file, 'w', encoding='utf-8') as f:
            yaml.dump(prompts_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        LOGGER.info(f"Saved prompts to {prompts_file}")

        # Save test cases to batch directory
        test_cases_file = batch_dir / 'test_cases.json'
        with open(test_cases_file, 'w', encoding='utf-8') as f:
            json.dump(test_cases, f, indent=2, ensure_ascii=False)
        LOGGER.info(f"Saved test cases to {test_cases_file}")

    # Run evaluations
    LOGGER.info(f"Starting evaluation of {len(test_cases)} test cases...")
    if not args.skip_grading:
        LOGGER.info(f"LLM grading enabled using model: {GRADING_MODEL}")
    else:
        LOGGER.info("LLM grading disabled")

    all_run_results = []
    total_errors = 0

    for run_num in range(1, num_runs + 1):
        if num_runs > 1:
            print(f"\n{'='*70}")
            print(f"STARTING RUN {run_num}/{num_runs}")
            print(f"{'='*70}\n")
            LOGGER.info(f"Starting run {run_num}/{num_runs}")

        # Create run directory
        run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if num_runs > 1:
            run_dir = batch_dir / f"run_{run_num}_{run_timestamp}"
        else:
            run_dir = batch_dir / run_timestamp
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save prompts and test cases to individual run folder
        prompts_file = run_dir / 'prompts.yaml'
        with open(prompts_file, 'w', encoding='utf-8') as f:
            yaml.dump(prompts_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        test_cases_file = run_dir / 'test_cases.json'
        with open(test_cases_file, 'w', encoding='utf-8') as f:
            json.dump(test_cases, f, indent=2, ensure_ascii=False)

        # Run evaluation
        results_summary = asyncio.run(run_evaluation(
            test_cases=test_cases,
            output_dir=run_dir,
            timeout_seconds=args.timeout,
            skip_grading=args.skip_grading
        ))

        # Save summary
        summary_file = run_dir / 'summary.json'
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(results_summary, f, indent=2, ensure_ascii=False)

        all_run_results.append(results_summary)
        total_errors += results_summary.get('errors', 0)

        # Print run summary
        print(f"\n{'='*70}")
        if num_runs > 1:
            print(f"RUN {run_num}/{num_runs} COMPLETE")
        else:
            print("EVALUATION COMPLETE")
        print("="*70)
        print(f"Run ID: {results_summary['run_id']}")
        print(f"Total tests: {results_summary['total_tests']}")
        print(f"Completed: {results_summary['completed']}")
        print(f"Errors: {results_summary['errors']}")
        print(f"Grading: {'Enabled' if results_summary['grading_enabled'] else 'Disabled'}")
        print(f"Results saved to: {run_dir}")
        print("="*70)

        # Print individual test results for this run
        print("\nTest Results:")
        print("-"*70)
        for tr in results_summary['test_results']:
            status = "✓" if not tr.get('error') else "✗"
            duration = tr.get('duration_seconds', 0)
            avg_score = tr.get('avg_score', None)

            score_str = f" [Avg: {avg_score:.1f}/5]" if avg_score else ""
            print(f"  {status} {tr['test_id']}: {duration:.2f}s{score_str}")

            if tr.get('error'):
                print(f"      Error: {tr['error'][:60]}...")

            # Print individual metric scores
            if tr.get('scores'):
                scores_display = ", ".join([f"{k.replace('metric_', 'M')}:{v}" for k, v in sorted(tr['scores'].items())])
                print(f"      Scores: {scores_display}")

        # Print run's overall score
        if results_summary['grading_enabled']:
            all_avg_scores = [tr['avg_score'] for tr in results_summary['test_results'] if tr.get('avg_score')]
            if all_avg_scores:
                overall_avg = sum(all_avg_scores) / len(all_avg_scores)
                print("\n" + "="*70)
                print(f"RUN {run_num} AVERAGE SCORE: {overall_avg:.2f}/5")
                print(f"Tests graded: {len(all_avg_scores)}/{results_summary['total_tests']}")
                print("="*70)

    # Multi-run aggregation
    if num_runs > 1:
        print("\n" + "="*70)
        print("AGGREGATING RESULTS ACROSS ALL RUNS...")
        print("="*70 + "\n")

        aggregation = aggregate_multi_run_results(all_run_results, batch_dir)

        # Print aggregated summary
        print("\n" + "="*70)
        print(f"MULTI-RUN EVALUATION COMPLETE ({num_runs} runs)")
        print("="*70)
        print(f"Batch directory: {batch_dir}")
        print(f"Total runs: {num_runs}")
        print(f"Total errors across all runs: {total_errors}")
        print("="*70)

        # Print aggregated test results
        print("\nAggregated Test Scores (mean ± std dev):")
        print("-"*70)
        for test_stat in aggregation.get('test_statistics', []):
            test_id = test_stat.get('test_id', 'Unknown')
            overall = test_stat.get('overall', {})
            mean = overall.get('mean', 0)
            std = overall.get('std_dev', 0)
            runs = test_stat.get('runs_with_scores', 0)
            print(f"  {test_id}: {mean:.2f} ± {std:.2f} ({runs} runs)")

        # Print category statistics
        cat_stats = aggregation.get('category_statistics', {})
        if cat_stats:
            print("\nCategory Statistics:")
            print("-"*70)
            for category, stats in sorted(cat_stats.items()):
                mean = stats.get('mean', 0)
                std = stats.get('std_dev', 0)
                count = stats.get('test_count', 0)
                print(f"  {category}: {mean:.2f} ± {std:.2f} ({count} tests)")

        # Print overall statistics
        overall_stats = aggregation.get('overall_statistics', {})
        if overall_stats:
            print("\n" + "="*70)
            print(f"OVERALL AGGREGATED SCORE: {overall_stats.get('mean', 0):.2f} ± {overall_stats.get('std_dev', 0):.2f}")
            print(f"Score range: {overall_stats.get('min', 0):.2f} - {overall_stats.get('max', 0):.2f}")
            print(f"Tests scored: {overall_stats.get('tests_scored', 0)}")
            print("="*70)
            print(f"\nSee {batch_dir / 'multi_run_aggregation.json'} for detailed statistics")
            print(f"See {batch_dir / 'multi_run_scores.csv'} for CSV summary")
        print("="*70)

        return 0 if total_errors == 0 else 1

    # Single run - print final analysis if available
    results_summary = all_run_results[0] if all_run_results else {}
    if results_summary.get('grading_enabled'):
        all_avg_scores = [tr['avg_score'] for tr in results_summary.get('test_results', []) if tr.get('avg_score')]
        if all_avg_scores:
            overall_avg = sum(all_avg_scores) / len(all_avg_scores)
            print("\n" + "="*70)
            print(f"OVERALL AVERAGE SCORE: {overall_avg:.2f}/5")
            print(f"Tests graded: {len(all_avg_scores)}/{results_summary.get('total_tests', 0)}")
            print("="*70)

        # Print final analysis if available
        final_analysis = results_summary.get('final_analysis', {})
        if final_analysis.get('success'):
            analysis = final_analysis.get('analysis', {})
            print("\n" + "="*70)
            print("FINAL ANALYSIS")
            print("="*70)

            if analysis.get('performance_summary'):
                print(f"\n{analysis['performance_summary']}")

            if analysis.get('strengths'):
                print("\nStrengths:")
                for s in analysis['strengths'][:3]:
                    print(f"  + {s}")

            if analysis.get('weaknesses'):
                print("\nWeaknesses:")
                for w in analysis['weaknesses'][:3]:
                    print(f"  - {w}")

            if analysis.get('critical_issues'):
                print("\nCritical Issues:")
                for issue in analysis['critical_issues'][:3]:
                    print(f"  ! {issue}")

            if analysis.get('recommendations'):
                print("\nTop Recommendations:")
                for rec in analysis['recommendations'][:3]:
                    priority = rec.get('priority', 'medium').upper()
                    area = rec.get('area', '')
                    suggestion = rec.get('suggestion', '')
                    print(f"  [{priority}] {area}: {suggestion[:60]}...")

            print("\n" + "="*70)
            print("See final_analysis.json for detailed analysis")
            print("See scores.csv and scores.json for aggregated scores")
            print("="*70)

    return 0 if results_summary['errors'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
