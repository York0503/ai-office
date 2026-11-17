# -*- coding: utf-8 -*-
"""AI 辦公室共用設定與安全工具（hooks 和 scripts 都用這一份）。

讀設定的順序：環境變數 → config/office.json（不上傳）→ config/office.example.json（範本）。
"""
import fnmatch
import json
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

ENV_MAP = {
    # 環境變數            設定位置                         型別
    "OFFICE_INGEST_URL":   (("monitor", "ingest_url"), str),
    "OFFICE_INGEST_TOKEN": (("monitor", "ingest_token"), str),
    "OFFICE_SEND_THINKING": (("monitor", "send_thinking"), bool),
    "OFFICE_MAX_DISPATCH": (("limits", "max_dispatch_per_round"), int),
    "OFFICE_TOOL_REPO":    (("guard", "tool_repo"), str),
}


def _read_json(rel):
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v not in ("", None):
            out[k] = v
    return out


def load():
    cfg = _merge(_read_json("config/office.example.json"), _read_json("config/office.json"))
    for name, (path, kind) in ENV_MAP.items():
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            continue
        raw = raw.strip()
        if kind is bool:
            val = raw.lower() not in ("0", "false", "no", "off")
        elif kind is int:
            try:
                val = int(raw)
            except ValueError:
                continue
        else:
            val = raw
        cfg.setdefault(path[0], {})[path[1]] = val
    return cfg


# ---------------- 組織表與系統訊息 ----------------

SYSTEM_PROMPT_PREFIXES = ("<agent-message", "<task-notification", "<system-reminder", "<command-")


def is_system_prompt(prompt):
    """部屬交回結果、背景任務通知這類由系統產生的訊息，不是使用者交代的新事情。"""
    p = (prompt or "").lstrip()
    return p.startswith(SYSTEM_PROMPT_PREFIXES) or "[Subagent hand-back]" in p[:200]


def load_roster():
    """回傳 (角色表, 每個角色可以派的人)；老闆可以派專案經理和所有部門主管。"""
    data = _read_json("office/src/roster.json")
    roles = {r["slug"]: r for r in data.get("roles", [])}
    allowed = {slug: set() for slug in roles}
    for r in roles.values():
        parent = r.get("parent")
        if parent:
            allowed.setdefault(parent, set()).add(r["slug"])
    return roles, allowed


# ---------------- 敏感資料 ----------------

SENSITIVE_NAMES = {".env", ".dev.vars", "office.json", "credentials", "credentials.json",
                   ".npmrc", ".pypirc", ".netrc", ".git-credentials"}
SENSITIVE_SUFFIX = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".ppk")
SAFE_TEMPLATE_SUFFIX = (".example", ".sample", ".template", ".example.json")


def is_sensitive_path(path, allow_templates=False):
    name = str(path or "").replace("\\", "/").rstrip("/").split("/")[-1].lower()
    if not name:
        return False
    if allow_templates and (name.endswith(SAFE_TEMPLATE_SUFFIX) or ".example." in name):
        return False
    if name in SENSITIVE_NAMES or name.startswith(".env."):
        return True
    if name.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")) and not name.endswith(".pub"):
        return True
    if name.endswith(SENSITIVE_SUFFIX):
        return True
    return bool(re.match(r"^(client[_-]?)?secrets?(\.[a-z0-9]+)*$", name)) or name.startswith("client_secret")


_KEYWORDS = r"(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|client[_-]?secret|credential|auth[_-]?key)"

# 明確的金鑰格式：commit 檢查和遮罩都用
STRICT_PATTERNS = [
    ("私鑰", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)")),
    ("API 金鑰", re.compile(r"\b(?:sk-ant-[A-Za-z0-9_\-]{10,}|sk-(?:proj-)?[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
                         r"|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_\-]{20,}|xox[abprs]-[A-Za-z0-9\-]{10,}"
                         r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{35}|hf_[A-Za-z0-9]{30,})\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("Authorization 標頭", re.compile(r"(?i)\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic|token)\s+[A-Za-z0-9._~+/=\-]{8,}")),
    ("密碼或金鑰設定", re.compile(r"(?i)\b[A-Za-z0-9_]*" + _KEYWORDS + r"[A-Za-z0-9_]*\s*[:=]\s*[\"'](?!\$\{|<|your|xxx|\*\*\*|changeme|example|placeholder|test)[A-Za-z0-9._~+/=\-]{12,}[\"']")),
    ("環境變數裡的金鑰", re.compile(r"(?m)^\s*(?:export\s+)?[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIAL)[A-Z0-9_]*\s*=\s*(?!\$|<|your|xxx|\*\*\*|changeme|example|placeholder|test)[^\s#()]{12,}\s*$")),
    ("JSON 裡的金鑰", re.compile(r"(?i)\"[^\"\n]*" + _KEYWORDS + r"[^\"\n]*\"\s*:\s*\"(?!\$\{|<|your|xxx|\*\*\*|changeme|example|placeholder|test)[^\"\n]{12,}\"")),
]

# 遮罩時額外用：看起來像隨機金鑰的長字串（大小寫加數字、32 字以上）
KEYLIKE_STRING = re.compile(r"\b(?=[A-Za-z0-9_\-]{32,}\b)(?=[A-Za-z0-9_\-]*[A-Z])(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{32,}\b")

_MASK_RULES = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"), "***私鑰已遮罩***"),
    (STRICT_PATTERNS[1][1], "***"),
    (STRICT_PATTERNS[2][1], "***JWT***"),
    (re.compile(r"(?i)(\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=\-]+"), r"\1***"),
    (re.compile(r"(?i)(\b[A-Za-z0-9_]*" + _KEYWORDS + r"[A-Za-z0-9_]*\s*[:=]\s*[\"']?)([^\s\"',;]{8,})"), r"\1***"),
    (re.compile(r"(?i)(\"[^\"\n]*" + _KEYWORDS + r"[^\"\n]*\"\s*:\s*\")([^\"\n]{8,})(\")"), r"\1***\3"),
    (KEYLIKE_STRING, "***"),
]


def known_secret_values(cfg):
    vals = [cfg.get("monitor", {}).get("ingest_token"), cfg.get("monitor", {}).get("view_token"),
            cfg.get("cloudflare", {}).get("api_token")]
    return [v for v in vals if isinstance(v, str) and len(v) >= 8]


def mask_text(s, extra_values=()):
    if not isinstance(s, str) or not s:
        return s
    for v in extra_values:
        s = s.replace(v, "***")
    for rx, rep in _MASK_RULES:
        s = rx.sub(rep, s)
    return s


def mask_obj(v, extra_values=()):
    if isinstance(v, str):
        return mask_text(v, extra_values)
    if isinstance(v, list):
        return [mask_obj(x, extra_values) for x in v]
    if isinstance(v, dict):
        return {k: mask_obj(x, extra_values) for k, x in v.items()}
    return v


def find_secrets(text):
    """回傳 [(類型, 行號)]，給 commit 檢查用。"""
    hits = []
    for label, rx in STRICT_PATTERNS:
        for m in rx.finditer(text):
            hits.append((label, text.count("\n", 0, m.start()) + 1))
    return hits


# ---------------- 公開工具專案的檔案範圍 ----------------

def path_allowed(path, patterns):
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    for pat in patterns:
        if pat.endswith("/**"):
            if p.startswith(pat[:-3] + "/"):
                return True
        elif fnmatch.fnmatchcase(p, pat):
            return True
    return False


def repo_slug_from_url(url):
    u = (url or "").strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    u = u.replace(":", "/")
    parts = [x for x in u.split("/") if x]
    return "/".join(parts[-2:]) if len(parts) >= 2 else ""


def is_tool_repo(slug, tool_repo):
    if not slug or not tool_repo:
        return False
    tool_repo = tool_repo.strip().lower()
    slug = slug.lower()
    return slug == tool_repo if "/" in tool_repo else slug.split("/")[-1] == tool_repo


# ---------------- 送事件到監控後台 ----------------

def post_events(cfg, events, wait=True):
    url = (cfg.get("monitor", {}).get("ingest_url") or "").strip()
    if not url:
        return
    token = (cfg.get("monitor", {}).get("ingest_token") or "").strip()
    data = json.dumps({"events": events}, ensure_ascii=False).encode()
    args = ["curl", "-sS", "-m", "8", "-o", "/dev/null", "-X", "POST", "-H", "Content-Type: application/json"]
    if token:
        args += ["-H", f"Authorization: Bearer {token}"]
    args += ["--data-binary", "@-", url]
    try:
        if wait:
            subprocess.run(args, input=data, capture_output=True, timeout=10)
        else:
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            p.stdin.write(data)
            p.stdin.close()
    except Exception:
        pass
