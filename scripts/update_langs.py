"""Gera o cartão de linguagens mais usadas e atualiza o README.

Soma os bytes de cada linguagem (API do GitHub) em todos os repositórios
públicos do usuário que não são forks, gera assets/top-langs-dark.svg e
assets/top-langs-light.svg e atualiza o trecho entre os marcadores
<!--TOP_LANG:START--> e <!--TOP_LANG:END--> do README.

Uso: GH_USER=M0abl1 GITHUB_TOKEN=... python scripts/update_langs.py
Apenas biblioteca padrão; nenhuma dependência externa.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
USER = os.environ.get("GH_USER", "M0abl1")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
TOP_N = 8
MARKERS = re.compile(r"(<!--TOP_LANG:START-->)(.*?)(<!--TOP_LANG:END-->)", re.S)
OTHER_COLOR = "#8B949E"

# Cores do GitHub Linguist (https://github.com/github-linguist/linguist).
COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Go": "#00ADD8",
    "HTML": "#e34c26", "CSS": "#663399", "SCSS": "#c6538c", "Dart": "#00B4AB", "PHP": "#4F5D95",
    "Blade": "#f7523f", "Kotlin": "#A97BFF", "Swift": "#F05138", "C++": "#f34b7d", "C": "#555555",
    "GDScript": "#355570", "Java": "#b07219", "Shell": "#89e051", "PowerShell": "#012456",
    "Objective-C": "#438eff", "Vue": "#41b883", "Rust": "#dea584", "C#": "#178600",
    "Dockerfile": "#384d54", "Batchfile": "#C1F12E", "CMake": "#DA3434", "Mako": "#7e858d",
}
THEMES = {
    "dark": {"title": "#58A6FF", "text": "#C9D1D9", "muted": "#8B949E", "track": "#30363D"},
    "light": {"title": "#0969DA", "text": "#1F2328", "muted": "#656D76", "track": "#D0D7DE"},
}


def api(url, attempts=5):
    """GET com novas tentativas limitadas para falhas de rede, 5xx e limite de API."""
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-langs"})
        if TOKEN:
            req.add_header("Authorization", f"Bearer {TOKEN}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            retryable = exc.code >= 500 or exc.code == 429 or (
                exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0")
            if not retryable or attempt == attempts:
                raise
            wait = retry_delay(exc.headers, attempt)
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
            wait = 2 ** attempt
        print(f"Falha ao acessar a API (tentativa {attempt}); nova tentativa em {wait}s.")
        time.sleep(wait)
    raise RuntimeError("inalcançável")


def retry_delay(headers, attempt):
    if headers.get("Retry-After", "").isdigit():
        return min(int(headers["Retry-After"]), 300)
    reset = headers.get("X-RateLimit-Reset", "")
    if reset.isdigit():
        return max(1, min(int(reset) - int(time.time()) + 1, 300))
    return 2 ** attempt


def collect():
    totals, page = {}, 1
    while True:
        repos = api(f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}")
        if not repos:
            break
        for repo in repos:
            if repo["fork"] or repo["private"]:
                continue
            for lang, size in api(repo["languages_url"]).items():
                totals[lang] = totals.get(lang, 0) + size
        page += 1
    return totals


def ranking(totals):
    """Top N com porcentagem sobre o total geral, mais a fatia 'Outras'."""
    total = sum(totals.values())
    if not total:
        raise SystemExit("Nenhuma linguagem encontrada; nada foi alterado.")
    ordered = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [(name, size * 100 / total) for name, size in ordered[:TOP_N]]
    other = sum(size for _, size in ordered[TOP_N:]) * 100 / total
    return top, other


def pct(value):
    return f"{value:.1f}".replace(".", ",") + "%"


def svg(langs, other, theme, updated):
    c = THEMES[theme]
    width, pad, bar_y = 360, 20, 52
    rows = (len(langs) + 1) // 2
    height = bar_y + 26 + rows * 24 + 30
    inner = width - 2 * pad
    parts, x = [], pad
    for name, p in langs + ([("Outras", other)] if other > 0 else []):
        w = inner * p / 100
        color = OTHER_COLOR if name == "Outras" else COLORS.get(name, OTHER_COLOR)
        parts.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" height="10" fill="{color}"><title>{escape(name)}: {pct(p)}</title></rect>')
        x += w
    items = []
    for i, (name, p) in enumerate(langs):
        col, row = i % 2, i // 2
        ix, iy = pad + col * (inner / 2), bar_y + 34 + row * 24
        items.append(
            f'<g><title>{escape(name)}: {pct(p)}</title>'
            f'<circle cx="{ix + 5}" cy="{iy - 4}" r="5" fill="{COLORS.get(name, OTHER_COLOR)}"/>'
            f'<text x="{ix + 16}" y="{iy}" class="t">{escape(name)} <tspan class="m">{pct(p)}</tspan></text></g>'
        )
    footer = f"Atualizado automaticamente em {updated}"
    if other > 0:
        footer += f" · outras linguagens: {pct(other)}"
    top = langs[0]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Linguagens mais usadas</title>
<desc id="desc">Mais usada: {escape(top[0])} ({pct(top[1])}). Atualizado em {updated}.</desc>
<style>
.h{{font:600 17px 'Segoe UI',Ubuntu,sans-serif;fill:{c['title']}}}
.t{{font:400 13px 'Segoe UI',Ubuntu,sans-serif;fill:{c['text']}}}
.m{{fill:{c['muted']}}}
.f{{font:400 11px 'Segoe UI',Ubuntu,sans-serif;fill:{c['muted']}}}
</style>
<text x="{pad}" y="32" class="h">Linguagens mais usadas</text>
<clipPath id="bar"><rect x="{pad}" y="{bar_y}" width="{inner}" height="10" rx="5"/></clipPath>
<rect x="{pad}" y="{bar_y}" width="{inner}" height="10" rx="5" fill="{c['track']}"/>
<g clip-path="url(#bar)">{''.join(parts)}</g>
{''.join(items)}
<text x="{pad}" y="{height - 12}" class="f">{escape(footer)}</text>
</svg>
"""


def main():
    # Valida o README antes de qualquer escrita: exatamente um par de marcadores, na ordem.
    readme = README.read_text(encoding="utf-8")
    if (readme.count("<!--TOP_LANG:START-->") != 1 or readme.count("<!--TOP_LANG:END-->") != 1
            or not MARKERS.search(readme)):
        raise SystemExit("README.md precisa de exatamente um par <!--TOP_LANG:START--> ... <!--TOP_LANG:END-->.")

    langs, other = ranking(collect())
    updated = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    top = langs[0]
    new_readme = MARKERS.sub(lambda m: f"{m.group(1)}**{top[0]}** ({pct(top[1])}){m.group(3)}", readme)
    (ROOT / "assets").mkdir(exist_ok=True)
    for theme in THEMES:
        (ROOT / "assets" / f"top-langs-{theme}.svg").write_text(svg(langs, other, theme, updated), encoding="utf-8", newline="\n")
    README.write_text(new_readme, encoding="utf-8", newline="\n")

    for name, p in langs:
        print(f"{name:12} {pct(p)}")
    print(f"{'Outras':12} {pct(other)}")


if __name__ == "__main__":
    main()
