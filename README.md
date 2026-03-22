# Comfyui-Subgraph_to_Node_Converter


ComfyUI Subgraph → Node Converter
A single-file ComfyUI custom node that converts any subgraph saved inside a workflow JSON into a real, installable Python custom node — without ever leaving ComfyUI.

Install
Drop comfyui_subgraph_to_node.py into ComfyUI/custom_nodes/ and restart.
No folder, no __init__.py, no pip installs required.

Find the node under: utils/subgraph → "Subgraph → Node Converter"

Quick Start
In ComfyUI, build your subgraph and save the workflow as .json into ComfyUI/input/

Add the Subgraph → Node Converter node to any workflow

Select your file from the json_file dropdown

Fill in naming fields (or leave blank to use the subgraph name)

Set dry_run = True and connect generated_code → Show Text to preview

Flip dry_run = False and queue — files are written

Restart ComfyUI — your new node appears in the category you chose

Sockets
Required
Widget	Type	Description
json_file	COMBO	Dropdown of .json files in ComfyUI/input/. Auto-refreshes when files are added.
output_directory	STRING	Where to write the generated node pack. Defaults to custom_nodes/subgraph_nodes/.
Optional
Widget	Type	Description
path_override	STRING	Absolute path to any .json file — overrides the picker entirely
subgraph_name	STRING	Which subgraph to convert when the workflow has multiple. Blank = auto-pick (first/only)
node_name	STRING	Internal key in NODE_CLASS_MAPPINGS — how ComfyUI identifies the node. Blank = subgraph name
display_name	STRING	Label shown in the Add Node menu and the node's title bar. Blank = node_name
category	STRING	Menu path. Use slashes for sub-menus, e.g. sampling/pipes. Blank = subgraph_nodes
class_name	STRING	Python class identifier in the generated .py. Blank = CamelCase(node_name) + Node
dry_run	BOOLEAN	Generate and preview code without writing any files (default: False)
Outputs
Socket	Type	Description
generated_code	STRING	Full source of the generated .py — pipe to Show Text to inspect before writing
output_path	STRING	Absolute path of the node file that was written
status	STRING	Detailed success summary (names, paths) or a full error message
Naming Fields Cheatsheet
text
subgraph name  →  "My KSampler Pipe"      (from the workflow JSON)

node_name      →  "MyKSamplerPipe"        NODE_CLASS_MAPPINGS key
display_name   →  "My KSampler Pipe"      Add-Node menu label
category       →  "sampling/pipes"        menu location
class_name     →  "MyKSamplerPipeNode"    Python class name in .py
All four fall back gracefully if left blank. The status output always echoes the resolved values so you know exactly what was used.

Supported Subgraph Formats
Format	Storage location	ComfyUI version
New subgraph	workflow["definitions"]["subgraphs"]	≥ Aug 2025
Legacy group node	workflow["extra"]["groupNodes"]	< Aug 2025
Bare subgraph file	The JSON file itself is the subgraph	any
Generated Output
Every run writes two files into output_directory:

File	Description
File	Description
<snake_node_name>_node.py	The custom node class
__init__.py	Package registration — re-scans all *_node.py files so multiple subgraphs can share the same output folder
Converting multiple subgraphs? Just point them all at the same output_directory. The __init__.py is regenerated each time and picks up every node in the folder.

After Converting
Make sure output_directory is inside (or symlinked into) ComfyUI/custom_nodes/

Restart ComfyUI

Your new node appears under the category you set

All internal nodes of the subgraph must already be installed — the generated node calls them at runtime via NODE_CLASS_MAPPINGS

Notes & Caveats
Hardcoded widget values baked into the subgraph are embedded as defaults in the generated node. Review them after generation.

Reroute / Note nodes inside the subgraph are skipped — they aren't executable node types.

The file picker (json_file dropdown) uses IS_CHANGED hashing and refreshes automatically whenever .json files are added to or removed from ComfyUI/input/.

The path_override field accepts ~ and environment variables (e.g. %USERPROFILE%\workflows\my_flow.json).
