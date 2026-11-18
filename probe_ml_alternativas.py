"""Testa, só leitura, os endpoints oficiais alternativos à busca bloqueada.

Uso (na raiz do projeto):
    python probe_ml_alternativas.py --i-approve-live-read-only-requests "fone bluetooth"
Mostra só status HTTP e contagens. Nunca imprime o token.
"""
import sys

import requests

import src.config  # noqa: F401  (carrega .env)
from src.integrations.mercadolivre_oauth import resolve_access_token

APPROVAL_FLAG = "--i-approve-live-read-only-requests"
args = sys.argv[1:]
if APPROVAL_FLAG not in args:
    sys.exit(f"Faz requisições reais (só leitura). Rode com {APPROVAL_FLAG} \"termo\"")
args = [a for a in args if a != APPROVAL_FLAG]
q = args[0] if args else "fone bluetooth"
tok = resolve_access_token()
if not tok.available:
    sys.exit("Sem token. Rode: python -m src.integrations.mercadolivre_oauth refresh")
H = {"Authorization": f"Bearer {tok.token.strip()}"}
API = "https://api.mercadolibre.com"


def get(path, **params):
    r = requests.get(API + path, headers=H, params=params, timeout=15)
    try:
        body = r.json()
    except ValueError:
        body = None
    return r.status_code, body


print(f"Busca de teste: {q!r} (token: {tok.source})\n")
s, b = get("/sites/MLB/domain_discovery/search", q=q, limit=3)
print(f"1. domain_discovery (descobre a categoria) -> HTTP {s}")
cat = None
if s == 200 and b:
    for d in b[:3]:
        print(f"   - {d.get('category_name')} ({d.get('category_id')})")
    cat = b[0].get("category_id")

if cat:
    s, b = get(f"/highlights/MLB/category/{cat}")
    n = len(b.get("content", [])) if isinstance(b, dict) else 0
    print(f"2. highlights (mais vendidos da categoria {cat}) -> HTTP {s}, {n} itens")
    if s == 200 and n:
        first = b["content"][0]
        kind, pid = first.get("type"), first.get("id")
        path = f"/products/{pid}" if kind == "PRODUCT" else f"/items/{pid}"
        s2, b2 = get(path)
        nome = (b2 or {}).get("name") or (b2 or {}).get("title")
        print(f"3. detalhe do 1o mais vendido ({kind}) -> HTTP {s2} {nome or ''}")
        if kind == "PRODUCT":
            s3, b3 = get(f"/products/{pid}/items")
            n3 = len((b3 or {}).get("results", [])) if isinstance(b3, dict) else 0
            print(f"4. vendedores desse produto (/products/id/items) -> HTTP {s3}, {n3} ofertas")
else:
    print("2. highlights: pulado (sem categoria)")

s, _ = get("/sites/MLB/search", q=q, limit=1)
print(f"\nControle: /sites/MLB/search -> HTTP {s} (403 = bloqueio confirmado)")
