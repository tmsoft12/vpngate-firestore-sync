import os
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime, timezone

VPNGATE_URL = "https://www.vpngate.net/api/iphone/"
CHUNK_SIZE = 700000
COLLECTION = "vpngate_list"
MIN_VALID_SIZE = 100_000

PROJECT_ID = os.environ["FIREBASE_PROJECT_ID"]
API_KEY = os.environ["FIREBASE_API_KEY"]

BASE = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    f"/databases/(default)/documents/{COLLECTION}"
)


def fetch_csv() -> str:
    req = urllib.request.Request(
        VPNGATE_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; vpngate-firestore-sync/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    # Dart tarafı String.fromCharCodes(bytes) kullanıyor — latin1 ile
    # bayt<->kod noktası birebir eşleşiyor, uygulamanın okuduğu yedekle
    # aynı kodlamada olması için burada da latin1.
    return raw.decode("latin1")


def patch_doc(doc_id: str, fields: dict):
    url = f"{BASE}/{doc_id}?key={API_KEY}"
    body = json.dumps({"fields": fields}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        print(e.read().decode("utf-8", "replace"), file=sys.stderr)
        raise


def main():
    try:
        text = fetch_csv()
    except Exception as e:
        print(f"VPN Gate'e ulaşılamadı: {e}", file=sys.stderr)
        sys.exit(1)

    # VPN Gate geçici bir hata/bakım sayfası döndürürse Firestore'daki son
    # iyi yedeği kötü veriyle ezmemek için: biçim ve boyut kontrolü.
    if not text.startswith("*vpn_servers") or len(text) < MIN_VALID_SIZE:
        print(
            f"Yanıt geçersiz görünüyor (uzunluk={len(text)}), yazma atlandı.",
            file=sys.stderr,
        )
        sys.exit(1)

    chunk_count = (len(text) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(chunk_count):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(text))
        patch_doc(f"chunk_{i}", {"data": {"stringValue": text[start:end]}})
        print(f"chunk_{i}: yazıldı ({end - start} karakter)")

    updated_at = datetime.now(timezone.utc).isoformat()
    patch_doc(
        "meta",
        {
            "chunkCount": {"integerValue": str(chunk_count)},
            "updatedAt": {"stringValue": updated_at},
        },
    )
    print(f"meta: yazıldı, chunkCount={chunk_count}, updatedAt={updated_at}")


if __name__ == "__main__":
    main()
