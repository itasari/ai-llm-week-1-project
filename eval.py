from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langsmith.evaluation import evaluate, LangChainStringEvaluator
from langsmith.schemas import Run, Example
from openai import OpenAI
import json
import os
import openai

from dotenv import load_dotenv
load_dotenv()

from langsmith.wrappers import wrap_openai
from langsmith import traceable

configurations = {
    "mistral_7B_instruct": {
        "endpoint_url": os.getenv("MISTRAL_7B_INSTRUCT_ENDPOINT"),
        "api_key": os.getenv("RUNPOD_API_KEY"),
        "model": "mistralai/Mistral-7B-Instruct-v0.3"
    },
    "openai_gpt-4o": {
        "endpoint_url": os.getenv("OPENAI_ENDPOINT"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4o"
    }
}

# Choose configuration
config_key = "openai_gpt-4o"
#config_key = "mistral_7B_instruct"

# Get selected configuration
config = configurations[config_key]

# Initialize the OpenAI client
client = wrap_openai(openai.Client(api_key=config["api_key"], base_url=config["endpoint_url"]))

@traceable
def prompt_evaluator(run: Run, example: Example) -> dict:
    inputs = example.inputs['input']
    outputs = example.outputs['output']

    # Add print statements to explore inputs and outputs
    print("Inputs here:")
    print(json.dumps(inputs, indent=2))
    print("\nOutputs here:")
    print(json.dumps(outputs, indent=2))

     # Extract system prompt
    system_prompt = next((msg['data']['content'] for msg in inputs if msg['type'] == 'system'), "")

    # Extract message history
    message_history = []
    for msg in inputs:
        if msg['type'] in ['human', 'ai']:
            message_history.append({
                "role": "user" if msg['type'] == 'human' else "assistant",
                "content": msg['data']['content']
            })

    # Extract latest user message and model output
    latest_message = message_history[-1]['content'] if message_history else ""
    model_output = outputs['data']['content']

    evaluation_prompt = f"""
    System Prompt: {system_prompt}

    Message History:
    {json.dumps(message_history, indent=2)}

    Latest User Message: {latest_message}

    Model Output: {model_output}

    Based on the above information, evaluate the model's output for: 

    1. compliance with the system prompt and context of the conversation
    Scoring criteria: Provide a score from 0 to 10, where 0 is completely non-compliant and 10 is perfectly compliant.
    Also provide a brief explanation for your score.

    2. student's engagement and progress in learning Chinese
    Scoring criteria:
    - Excellent: The model's output effectively engages the student in learning Chinese, addressing their needs and interests. 
    Student's showing significant progress in Chinese, where their answers are correct about 85% of the time.
    - Good: The model's output somewhat effectively engages the student in learning Chinese, but there are some areas that could be improved.
    Student's showing moderate progress in Chinese, where their answers are correct about 70% of the time.
    - Fair: The model's output does not effectively engage the student in learning Chinese.
    Student's showing minimal progress in Chinese, where their answers are correct about 60% of the time.
    - Poor: The model's output does not engage the student in learning Chinese. Student doesn't show enthusiasm for learning Chinese,
    and their answers are correct < 60% of the time.
    Please also provide a brief explanation for your score.

    You must respond in the following JSON format and all the values must not be null:
    {{
        "prompt_compliance_score": <int>,
        "prompt_compliance_explanation": "<string>"
        "engagement_and_progress_score": <string>,
        "engagement_and_progress_explanation": "<string>"
    }}
    """

    response = client.chat.completions.create(
        model=config["model"],
        messages=[
            {"role": "system", "content": "You are an AI assistant tasked with evaluating the compliance of model outputs to given prompts and conversation context, as well as the student's engagement and progress in learning Chinese."},
            {"role": "user", "content": evaluation_prompt}
        ],
        temperature=0.2
    )

    try:
        result = json.loads(response.choices[0].message.content)
        print(result)
        return {
            "results": [
                {
                    "key": "prompt_compliance",
                    "score": result["prompt_compliance_score"] / 10,  # Normalize to 0-1 range
                    "reason": result["prompt_compliance_explanation"],
                },
                {
                    "key": "engagement_and_progress",
                    "value": result["engagement_and_progress_score"],
                    "reason": result["engagement_and_progress_explanation"]
                }
            ]
        }
    except json.JSONDecodeError:
        return {
            "results": [
                {
                    "key": "prompt_compliance",
                    "score": 0,
                    "reason": "Failed to parse evaluator response",
                },
                {
                    "key": "engagement_and_progress",
                    "value": "Poor",
                    "reason": "Failed to parse evaluator response"
                }
            ]
        }

# The name or UUID of the LangSmith dataset to evaluate on. 
# This needs to match the dataset name in LangSmith.
data = "week-1-project-language-tutor"

# A string to prefix the experiment name with.
experiment_prefix = "Chinese tutoring prompt compliance"

# List of evaluators to score the outputs of target task
evaluators = [
    prompt_evaluator
]

# Evaluate the target task
results = evaluate(
    lambda inputs: inputs,
    data=data,
    evaluators=evaluators,
    experiment_prefix=experiment_prefix,
)

print(results)