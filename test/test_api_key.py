from openai import OpenAI

client = OpenAI(api_key="API_KEY_SAYA")

response = client.responses.create(
    model="gpt-4.1-mini",
    input="Halo"
)

print(response.output_text)