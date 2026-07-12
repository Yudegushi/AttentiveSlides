import os
import time

from openai import OpenAI


def main() -> None:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = os.environ.get(
        "DASHSCOPE_MODEL",
        "qwen3.7-plus",
    )

    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=120.0,
        max_retries=2,
    )

    started = time.perf_counter()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 AttentiveSlides 的 slide-grounded AI Tutor。"
                    "只能依据用户提供的 slide context 回答。"
                    "不要补充 context 中没有出现的事实。"
                    "使用中文，专业术语保留英文。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Slide sources:\n"
                    "[source_id: slide_02_aoi_01]\n"
                    "Fixation is maintaining gaze on a single location.\n"
                    "[source_id: slide_02_aoi_02]\n"
                    "Saccade is a rapid eye movement between fixations.\n\n"
                    "Question: fixation 和 saccade 有什么区别？"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=512,
        extra_body={
            "enable_thinking": False,
        },
    )

    latency = time.perf_counter() - started
    message = response.choices[0].message.content

    print("Model:", response.model)
    print("Latency:", round(latency, 2), "seconds")
    print("Response:")
    print(message)

    if response.usage:
        print("Prompt tokens:", response.usage.prompt_tokens)
        print("Completion tokens:", response.usage.completion_tokens)
        print("Total tokens:", response.usage.total_tokens)


if __name__ == "__main__":
    main()
