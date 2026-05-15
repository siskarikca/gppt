import requests
import time

# ============================
# MASUKKAN ACCESS TOKEN DI SINI
# ============================
ACCESS_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzQ0ZTY1LWJiYzktNDRkMS1hOWQwLWY5NTdiMDc5YmQwZSIsInR5cCI6IkpXVCJ9.XXXXXXXXX"

# ============================
# FILE INPUT & OUTPUT
# ============================
INPUT_FILE = "promo_codes.txt"    # File berisi daftar promo code (satu per baris)
OUTPUT_FILE = "hasil_promo.txt"   # File hasil pengecekan


def check_promo(promo_code: str) -> dict:
    """
    Check ChatGPT promo code eligibility.
    """
    url = f"https://chatgpt.com/backend-api/promotions/eligibility/{promo_code}"

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.6",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "oai-language": "en-US",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    params = {
        "type": "promo"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def main():
    # Baca promo codes dari file txt
    try:
        with open(INPUT_FILE, "r") as f:
            promo_codes = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"[ERROR] File '{INPUT_FILE}' tidak ditemukan!")
        print(f"Buat file '{INPUT_FILE}' dan isi dengan promo code (satu per baris).")
        return

    if not promo_codes:
        print(f"[ERROR] File '{INPUT_FILE}' kosong!")
        return

    print(f"Ditemukan {len(promo_codes)} promo code dari '{INPUT_FILE}'")
    print("=" * 50)

    results = []

    for i, code in enumerate(promo_codes, 1):
        print(f"[{i}/{len(promo_codes)}] Checking: {code} ...", end=" ")

        result = check_promo(code)

        if "error" in result:
            message = f"Error: {result['error']}"
        elif result.get("is_eligible"):
            message = "Eligible - Promo code valid!"
        else:
            reason = result.get("ineligible_reason", {})
            message = reason.get("message", "Unknown reason")

        print(message)
        results.append(f"{code} | {message}")

        # Delay kecil supaya tidak kena rate limit
        if i < len(promo_codes):
            time.sleep(1)

    # Simpan hasil ke file output
    with open(OUTPUT_FILE, "w") as f:
        f.write("HASIL CEK PROMO CODE\n")
        f.write("=" * 50 + "\n\n")
        for line in results:
            f.write(line + "\n")
        f.write("\n" + "=" * 50 + "\n")
        f.write(f"Total: {len(results)} promo code dicek\n")

    print("\n" + "=" * 50)
    print(f"Hasil disimpan ke '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
