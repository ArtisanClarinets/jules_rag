# Streamlit Critique & Improvement Loop Demo

This demo implements the "Automatic Critique + Improvement Loop" pattern using Groq's API.

It follows these steps:
1.  **Generate initial answer** (Pro Mode style: parallel candidates + synthesis).
2.  **Critique**: Have a critic model identify flaws and missing pieces.
3.  **Revise**: Revise the answer addressing all critiques.
4.  **Repeat**: Repeat the critique/revise loop for higher quality.

## Setup

1.  Navigate to this directory:
    ```bash
    cd examples/critique_loop
    ```

2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3.  Get a Groq API Key from [console.groq.com](https://console.groq.com).

## Running the App

You can run the app using Streamlit:

```bash
export GROQ_API_KEY="your_api_key_here"
streamlit run streamlit_app.py
```

Alternatively, you can enter your API key directly in the Streamlit UI sidebar.

You can also select the model to use from the sidebar (e.g., `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`).
