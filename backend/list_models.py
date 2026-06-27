import httpx
import backend.config as config

# Menggunakan API Key dan URL server LiteLLM Anda sendiri
headers = {
    "Authorization": f"Bearer {config.LOCAL_API_KEY}"
}

try:
    # Memanggil endpoint standar OpenAI / LiteLLM untuk list models
    r = httpx.get(
        f"{config.BASE_URL}/v1/models",
        headers=headers,
        timeout=30.0
    )

    print(f"Status Code: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        print("\n=== DAFTAR MODEL YANG TERSEDIA ===")
        # Menampilkan ID model yang aktif di server Anda
        for model in data.get("data", []):
            print(f"- {model.get('id')}")
    else:
        print("Gagal mengambil data model:")
        print(r.text[:1000])

except Exception as e:
    print(f"Terjadi kesalahan saat koneksi ke server: {e}")