"""Minimal S-expression reader/writer for KiCad files."""


class Sym(str):
    """An unquoted atom. Plain str means a quoted string."""


def parse(text):
    pos = 0
    n = len(text)
    stack = [[]]
    while pos < n:
        c = text[pos]
        if c in " \t\r\n":
            pos += 1
        elif c == "(":
            stack.append([])
            pos += 1
        elif c == ")":
            done = stack.pop()
            stack[-1].append(done)
            pos += 1
        elif c == '"':
            pos += 1
            out = []
            while text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                    out.append({"n": "\n", "t": "\t"}.get(text[pos], text[pos]))
                else:
                    out.append(text[pos])
                pos += 1
            pos += 1
            stack[-1].append("".join(out))
        else:
            start = pos
            while pos < n and text[pos] not in ' \t\r\n()"':
                pos += 1
            stack[-1].append(Sym(text[start:pos]))
    return stack[0][0]


def _atom(a):
    if isinstance(a, Sym):
        return str(a)
    if isinstance(a, str):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(a, float):
        s = f"{a:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(a)


def dump(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    flat = "(" + " ".join(dump(x) if isinstance(x, list) else _atom(x) for x in node) + ")"
    if len(flat) <= 100 or not any(isinstance(x, list) for x in node):
        return flat
    pad = "\t" * (indent + 1)
    head = []
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        head.append(_atom(node[i]))
        i += 1
    lines = ["(" + " ".join(head)]
    for x in node[i:]:
        lines.append(pad + (dump(x, indent + 1) if isinstance(x, list) else _atom(x)))
    lines.append("\t" * indent + ")")
    return "\n".join(lines)


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def first(node, key, default=None):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return default
