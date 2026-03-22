"""
ComfyUI-SubgraphToNode  —  single-file drop-in
===============================================
Drop this file directly into  ComfyUI/custom_nodes/  and restart.
No folder, no __init__.py required.

Node location:  utils/subgraph  →  "Subgraph → Node Converter"

Inputs (required)
-----------------
  json_file         COMBO   — .json files found in ComfyUI/input/  (auto-refreshes)
  output_directory  STRING  — where to write the generated node pack

Inputs (optional)
-----------------
  path_override   STRING  — absolute path to any .json; overrides the picker
  subgraph_name   STRING  — which subgraph to convert (blank = auto-pick)
  node_name       STRING  — key in NODE_CLASS_MAPPINGS          (blank = subgraph name)
  display_name    STRING  — label in the Add-Node menu / title bar (blank = node_name)
  category        STRING  — menu path, e.g. "sampling/pipes"    (blank = subgraph_nodes)
  class_name      STRING  — Python class name in generated file  (blank = CamelCase+Node)
  dry_run         BOOL    — preview code without writing files

Outputs
-------
  generated_code  STRING  — full .py source  (pipe to Show Text to preview)
  output_path     STRING  — absolute path of the written file
  status          STRING  — success summary or error message
"""

import hashlib
import json
import os
import re
import textwrap
from collections import defaultdict, deque

# ── ComfyUI path helper ───────────────────────────────────────────────────────

def _input_dir() -> str:
    try:
        import folder_paths
        return folder_paths.get_input_directory()
    except Exception:
        return os.path.join(os.path.dirname(__file__), "..", "input")


def _default_output() -> str:
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), "subgraph_nodes")
    )


def _scan_json_files() -> list:
    d = _input_dir()
    if not os.path.isdir(d):
        return ["(no input dir found)"]
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".json"))
    return files or ["(no .json files in input/)"]


# ── Name utilities ────────────────────────────────────────────────────────────

def _snake(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower() or "_node"


def _camel(name: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[^a-zA-Z0-9]+", name) if w)


def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return ("_" + s) if s and s[0].isdigit() else s or "_x"


# ── Widget spec lookup ────────────────────────────────────────────────────────

_WIDGET = {
    "INT":     '("INT",     {"default": 0,   "min": -2147483648, "max": 2147483647})',
    "FLOAT":   '("FLOAT",   {"default": 0.0, "min": -1e9, "max": 1e9, "step": 0.01})',
    "STRING":  '("STRING",  {"default": "", "multiline": False})',
    "BOOLEAN": '("BOOLEAN", {"default": False})',
}

def _wspec(t: str) -> str:
    return _WIDGET.get(t, f'("{t}", {{}})')


# ── Boundary node types (not real ComfyUI nodes) ──────────────────────────────

_B_IN  = {"graph/input",  "GraphInput",  "subgraph/input",  "ComfyUI.GraphInput"}
_B_OUT = {"graph/output", "GraphOutput", "subgraph/output", "ComfyUI.GraphOutput"}


# ── Workflow / subgraph loading ───────────────────────────────────────────────

def _load_workflow(json_file: str, path_override: str) -> dict:
    override = path_override.strip()
    if override:
        path = os.path.expanduser(os.path.expandvars(override))
    else:
        pick = json_file.strip()
        if not pick or pick.startswith("("):
            raise ValueError(
                "No JSON selected and path_override is empty.\n"
                "Save your workflow into ComfyUI/input/ or fill in path_override."
            )
        path = os.path.join(_input_dir(), pick)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _pick_subgraph(workflow: dict, target: str) -> dict:
    # new format
    pool = workflow.get("definitions", {}).get("subgraphs", [])
    # legacy group-node format
    if not pool:
        gn = workflow.get("extra", {}).get("groupNodes", {})
        pool = [{"name": k, **v} for k, v in gn.items()] if gn else []
    # bare subgraph file
    if not pool:
        if {"nodes", "links"}.issubset(workflow):
            return workflow
        raise ValueError("No subgraph definitions found in the workflow JSON.")

    if target.strip():
        for e in pool:
            if e.get("name") == target.strip():
                return e
        raise ValueError(
            f"Subgraph '{target}' not found. "
            f"Available: {[e.get('name','?') for e in pool]}"
        )
    if len(pool) == 1:
        return pool[0]
    names = [e.get("name", "?") for e in pool]
    print(f"[SubgraphToNode] Multiple subgraphs: {names}. Using '{pool[0].get('name')}'.")
    return pool[0]


# ── Graph analysis ────────────────────────────────────────────────────────────

def _parse_links(raw: list) -> dict:
    """Return {link_id: (src_node, src_slot, dst_node, dst_slot)}."""
    out = {}
    for lnk in raw:
        if isinstance(lnk, list) and len(lnk) >= 5:
            out[lnk[0]] = (lnk[1], lnk[2], lnk[3], lnk[4])
    return out


def _topo(nodes: list, lmap: dict) -> list:
    """Kahn's topological sort — returns node dicts in execution order."""
    ids   = {n["id"] for n in nodes}
    indeg = defaultdict(int)
    adj   = defaultdict(list)
    for src, _, dst, __ in lmap.values():
        if src in ids and dst in ids:
            adj[src].append(dst)
            indeg[dst] += 1
    queue = deque(n["id"] for n in nodes if indeg[n["id"]] == 0)
    order, nmap = [], {n["id"]: n for n in nodes}
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nb in adj[nid]:
            indeg[nb] -= 1
            if indeg[nb] == 0:
                queue.append(nb)
    order.extend({n["id"] for n in nodes} - set(order))   # handle any cycles
    return [nmap[nid] for nid in order if nid in nmap]


# ── Code generator ────────────────────────────────────────────────────────────

def _generate(sg: dict, node_name: str, display_name: str,
              category: str, class_name: str) -> str:

    sg_name = sg.get("name", "MySubgraph")

    # Resolve effective names
    node_name    = node_name.strip()    or sg_name
    display_name = display_name.strip() or node_name
    category     = category.strip()     or "subgraph_nodes"
    class_name   = class_name.strip()   or (_camel(node_name) + "Node")
    fn_name      = _snake(node_name)

    sg_inputs  = sg.get("inputs",  [])
    sg_outputs = sg.get("outputs", [])
    nodes      = sg.get("nodes",   [])
    raw_links  = sg.get("links",   [])

    lmap      = _parse_links(raw_links)
    sorted_nd = _topo(nodes, lmap)
    b_in      = {n["id"]: n for n in nodes if n.get("type") in _B_IN}
    b_out     = {n["id"]: n for n in nodes if n.get("type") in _B_OUT}

    # INPUT_TYPES
    params, req = [], []
    for idx, inp in enumerate(sg_inputs):
        p = _ident(inp.get("name", f"input_{idx}"))
        params.append(p)
        req.append(f'                "{p}": {_wspec(inp.get("type","STRING"))},')

    ret_types = tuple(o.get("type", "IMAGE") for o in sg_outputs)
    ret_names = tuple(_ident(o.get("name", f"out_{i}")) for i, o in enumerate(sg_outputs))

    # Execute body
    I = "        "
    body = [
        f"{I}from nodes import NODE_CLASS_MAPPINGS as _NCM",
        f"{I}_R: dict = {{}}",
        f"{I}_ext = [{', '.join(params) if params else ''}]",
        "",
    ]

    for nd in sorted_nd:
        nid, ntype = nd["id"], nd.get("type", "")
        if ntype in (_B_IN | _B_OUT):
            continue

        nv, rv = f"_n{nid}", f"_r{nid}"
        body.append(f"{I}# {ntype}  (id={nid})")

        kw, wc = [], 0
        for slot, inp_def in enumerate(nd.get("inputs", [])):
            p   = _ident(inp_def.get("name", f"in_{slot}"))
            lid = inp_def.get("link")
            if lid is not None:
                e = lmap.get(lid)
                if e:
                    src, ss, _, __ = e
                    if src in b_in:
                        ext_i = ss if ss < len(sg_inputs) else 0
                        kw.append(f"                {p}=_ext[{ext_i}],")
                    else:
                        kw.append(f"                {p}=_R.get({src},(None,))[{ss}],")
                else:
                    kw.append(f"                # {p}: unresolved link {lid}")
            else:
                wvals = nd.get("widgets_values", [])
                if wc < len(wvals):
                    kw.append(f"                {p}={repr(wvals[wc])},")
                    wc += 1

        body += [
            f"{I}{nv} = _NCM['{ntype}']()",
            f"{I}_fn = getattr(_NCM['{ntype}'], 'FUNCTION', 'execute')",
            f"{I}try:",
            f"{I}    {rv} = getattr({nv}, _fn)(",
            *kw,
            f"{I}    )",
            f"{I}except Exception as _e:",
            f"{I}    raise RuntimeError(f\"Node '{ntype}' (id={nid}) failed: {{_e}}\") from _e",
            f"{I}_R[{nid}] = {rv}",
            "",
        ]

    # Return tuple
    ret_exprs = []
    for out_def in sg_outputs:
        rl = out_def.get("link") or (out_def.get("links") or [None])[0]
        if rl is not None and rl in lmap:
            src, ss, _, __ = lmap[rl]
            if src in b_out:
                ob = b_out[src].get("inputs", [])
                if ob:
                    back = ob[0].get("link")
                    if back and back in lmap:
                        src, ss, _, __ = lmap[back]
            ret_exprs.append(f"_R.get({src},(None,))[{ss}]")
        else:
            ret_exprs.append("None")

    body.append(f"{I}return ({', '.join(ret_exprs)},)")

    req_block  = "\n".join(req) if req else "                # (no inputs)"
    body_block = "\n".join(body)
    psig       = (", " + ", ".join(params)) if params else ""

    return textwrap.dedent(f"""\
        \"\"\"
        Auto-generated ComfyUI custom node
          Source subgraph : {sg_name}
          node_name       : {node_name}
          display_name    : {display_name}
          category        : {category}
          class_name      : {class_name}
        \"\"\"


        class {class_name}:
            \"\"\"{display_name} — generated from subgraph '{sg_name}'.\"\"\"

            @classmethod
            def INPUT_TYPES(cls):
                return {{
                    "required": {{
        {req_block}
                    }},
                }}

            RETURN_TYPES = {repr(ret_types)}
            RETURN_NAMES = {repr(ret_names)}
            FUNCTION     = "{fn_name}"
            CATEGORY     = "{category}"
            OUTPUT_NODE  = False

            def {fn_name}(self{psig}):
        {body_block}


        NODE_CLASS_MAPPINGS        = {{"{node_name}": {class_name}}}
        NODE_DISPLAY_NAME_MAPPINGS = {{"{node_name}": "{display_name}"}}
        """)


def _write_init(out_dir: str) -> str:
    """Regenerate __init__.py to import every *_node.py in out_dir."""
    node_files = sorted(f for f in os.listdir(out_dir) if f.endswith("_node.py"))
    lines = ["# Auto-generated by ComfyUI-SubgraphToNode\n"]
    maps, disp = [], []
    for f in node_files:
        m = os.path.splitext(f)[0]
        lines += [
            f"from .{m} import NODE_CLASS_MAPPINGS as _{m}_ncm",
            f"from .{m} import NODE_DISPLAY_NAME_MAPPINGS as _{m}_dn",
        ]
        maps.append(f"    **_{m}_ncm,")
        disp.append(f"    **_{m}_dn,")
    lines += [
        "",
        "NODE_CLASS_MAPPINGS = {", *maps, "}",
        "NODE_DISPLAY_NAME_MAPPINGS = {", *disp, "}",
        '__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]',
    ]
    path = os.path.join(out_dir, "__init__.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


# ═════════════════════════════════════════════════════════════════════════════
# ComfyUI Node
# ═════════════════════════════════════════════════════════════════════════════

class SubgraphToNodeConverter:
    """Converts a ComfyUI subgraph into a real Python custom node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json_file": (
                    sorted(_scan_json_files()),
                    {"tooltip": "JSON files found in ComfyUI/input/ — auto-refreshes."},
                ),
                "output_directory": (
                    "STRING",
                    {
                        "default": _default_output(),
                        "multiline": False,
                        "tooltip": "Folder for generated files. Drop it in custom_nodes/ and restart.",
                    },
                ),
            },
            "optional": {
                "path_override": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Absolute path to any .json — overrides the picker.",
                    },
                ),
                "subgraph_name": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Subgraph to convert. Blank = auto-pick.",
                    },
                ),
                "node_name": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Key in NODE_CLASS_MAPPINGS. Blank = subgraph name.",
                    },
                ),
                "display_name": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Label in the Add-Node menu. Blank = node_name.",
                    },
                ),
                "category": (
                    "STRING",
                    {
                        "default": "subgraph_nodes",
                        "multiline": False,
                        "tooltip": 'Menu path, e.g. "image/processing". Slashes = sub-menus.',
                    },
                ),
                "class_name": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Python class name. Blank = CamelCase(node_name) + Node.",
                    },
                ),
                "dry_run": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Preview code without writing files.",
                    },
                ),
            },
        }

    RETURN_TYPES  = ("STRING", "STRING", "STRING")
    RETURN_NAMES  = ("generated_code", "output_path", "status")
    FUNCTION      = "convert"
    CATEGORY      = "utils/subgraph"
    OUTPUT_NODE   = True

    @classmethod
    def IS_CHANGED(cls, json_file, output_directory, **_):
        """Re-evaluate when the input/ directory changes (new .json files added)."""
        d = _input_dir()
        if not os.path.isdir(d):
            return float("nan")
        h = hashlib.md5()
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".json"):
                h.update(f.encode())
        return h.hexdigest()

    def convert(
        self,
        json_file:        str,
        output_directory: str,
        path_override:    str  = "",
        subgraph_name:    str  = "",
        node_name:        str  = "",
        display_name:     str  = "",
        category:         str  = "subgraph_nodes",
        class_name:       str  = "",
        dry_run:          bool = False,
    ):
        try:
            workflow = _load_workflow(json_file, path_override)
            sg       = _pick_subgraph(workflow, subgraph_name)
            code     = _generate(sg, node_name, display_name, category, class_name)

            eff_node    = node_name.strip()    or sg.get("name", "MySubgraph")
            eff_display = display_name.strip() or eff_node
            eff_cat     = category.strip()     or "subgraph_nodes"

            if dry_run:
                return (
                    code,
                    "(dry run — no files written)",
                    f"✅ Dry run OK\n"
                    f"   node_name    : {eff_node}\n"
                    f"   display_name : {eff_display}\n"
                    f"   category     : {eff_cat}",
                )

            out_dir = os.path.expanduser(os.path.expandvars(output_directory.strip()))
            os.makedirs(out_dir, exist_ok=True)

            node_file = os.path.join(out_dir, f"{_snake(eff_node)}_node.py")
            with open(node_file, "w", encoding="utf-8") as fh:
                fh.write(code)

            init_file = _write_init(out_dir)

            return (
                code,
                node_file,
                f"✅ Files written\n"
                f"   node     : {node_file}\n"
                f"   init     : {init_file}\n"
                f"   name     : {eff_node}\n"
                f"   display  : {eff_display}\n"
                f"   category : {eff_cat}\n"
                f"\n⚠️  Restart ComfyUI to load the new node.",
            )

        except Exception as exc:
            msg = f"❌ {type(exc).__name__}: {exc}"
            print(f"[SubgraphToNode] {msg}")
            return ("", "", msg)


# ─────────────────────────────────────────────────────────────────────────────
NODE_CLASS_MAPPINGS = {
    "SubgraphToNodeConverter": SubgraphToNodeConverter,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SubgraphToNodeConverter": "Subgraph → Node Converter",
}
